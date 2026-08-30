#include <arpa/inet.h>
#include <netinet/in.h>
#include <pthread.h>
#include <sys/socket.h>
#include <unistd.h>

#include <atomic>
#include <cerrno>
#include <chrono>
#include <condition_variable>
#include <ctime>
#include <cstdio>
#include <cstring>
#include <deque>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <mutex>
#include <random>
#include <sstream>
#include <string>
#include <thread>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace {

struct Packet {
  std::string type;
  std::string lb_id;
  std::string token;
  std::string sender_id;
  std::string receiver_id;
  long seq = 0;
  std::string payload;
};

struct StreamCounters {
  long tx_packets = 0;
  long tx_bytes = 0;
  long rx_packets = 0;
  long rx_bytes = 0;
  long dropped_packets = 0;
  double last_update_unix = 0.0;
};

struct WorkerCounters {
  long rx_datagrams = 0;
  long rx_datagram_bytes = 0;
  long parse_errors = 0;
  long register_messages = 0;
  long data_messages = 0;
  long forwarded = 0;
  long forwarded_bytes = 0;
  long dropped = 0;
  long send_errors = 0;
};

struct Datagram {
  sockaddr_in src{};
  std::string raw;
  long byte_len = 0;
};

struct Reservation {
  std::string token;
};

struct ReceiverAddr {
  sockaddr_in addr{};
  bool valid = false;
};

std::mutex g_mutex;
std::unordered_map<std::string, Reservation> g_reservations;  // lb_id -> reservation
std::unordered_map<std::string, StreamCounters> g_streams;      // lb_id|sender|receiver -> counters
std::unordered_map<std::string, ReceiverAddr> g_receivers;      // lb_id|receiver -> addr
std::vector<WorkerCounters> g_worker_counters;

std::vector<std::deque<Datagram>> g_worker_queues;
std::vector<std::unique_ptr<std::mutex>> g_worker_queue_mutexes;
std::vector<std::unique_ptr<std::condition_variable>> g_worker_queue_cvs;
std::atomic<unsigned long long> g_dispatch_rr{0};

std::string reservations_file;
std::string metrics_file;
int data_port = 18020;
double drop_rate = 0.0;
int workers = 2;
int flush_interval_ms = 100;
bool pin_workers = false;
int pin_base_cpu = 0;

std::atomic<bool> g_dirty{false};
std::atomic<bool> g_running{true};

std::string trim(const std::string& s) {
  size_t b = 0;
  while (b < s.size() && (s[b] == ' ' || s[b] == '\n' || s[b] == '\r' || s[b] == '\t')) {
    ++b;
  }
  size_t e = s.size();
  while (e > b && (s[e - 1] == ' ' || s[e - 1] == '\n' || s[e - 1] == '\r' || s[e - 1] == '\t')) {
    --e;
  }
  return s.substr(b, e - b);
}

std::string json_escape(const std::string& in) {
  std::string out;
  out.reserve(in.size() + 8);
  for (char c : in) {
    switch (c) {
      case '\\':
        out += "\\\\";
        break;
      case '"':
        out += "\\\"";
        break;
      case '\n':
        out += "\\n";
        break;
      case '\r':
        out += "\\r";
        break;
      case '\t':
        out += "\\t";
        break;
      default:
        out += c;
        break;
    }
  }
  return out;
}

bool extract_json_string(const std::string& json, const std::string& key, std::string* out) {
  const std::string needle = "\"" + key + "\"";
  size_t pos = json.find(needle);
  if (pos == std::string::npos) {
    return false;
  }
  pos = json.find(':', pos + needle.size());
  if (pos == std::string::npos) {
    return false;
  }
  ++pos;
  while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) {
    ++pos;
  }
  if (pos >= json.size() || json[pos] != '"') {
    return false;
  }
  ++pos;
  std::string val;
  while (pos < json.size()) {
    char c = json[pos++];
    if (c == '\\') {
      if (pos >= json.size()) {
        return false;
      }
      char esc = json[pos++];
      switch (esc) {
        case 'n':
          val.push_back('\n');
          break;
        case 'r':
          val.push_back('\r');
          break;
        case 't':
          val.push_back('\t');
          break;
        case '\\':
          val.push_back('\\');
          break;
        case '"':
          val.push_back('"');
          break;
        default:
          val.push_back(esc);
          break;
      }
      continue;
    }
    if (c == '"') {
      *out = val;
      return true;
    }
    val.push_back(c);
  }
  return false;
}

bool extract_json_long(const std::string& json, const std::string& key, long* out) {
  const std::string needle = "\"" + key + "\"";
  size_t pos = json.find(needle);
  if (pos == std::string::npos) {
    return false;
  }
  pos = json.find(':', pos + needle.size());
  if (pos == std::string::npos) {
    return false;
  }
  ++pos;
  while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) {
    ++pos;
  }
  size_t end = pos;
  while (end < json.size() && ((json[end] >= '0' && json[end] <= '9') || json[end] == '-')) {
    ++end;
  }
  if (end == pos) {
    return false;
  }
  try {
    *out = std::stol(json.substr(pos, end - pos));
    return true;
  } catch (...) {
    return false;
  }
}

bool parse_packet(const std::string& raw, Packet* pkt) {
  if (!extract_json_string(raw, "type", &pkt->type)) {
    return false;
  }
  extract_json_string(raw, "lb_id", &pkt->lb_id);
  extract_json_string(raw, "token", &pkt->token);
  extract_json_string(raw, "sender_id", &pkt->sender_id);
  extract_json_string(raw, "receiver_id", &pkt->receiver_id);
  extract_json_long(raw, "seq", &pkt->seq);
  extract_json_string(raw, "payload", &pkt->payload);
  return true;
}

std::string key_stream(const std::string& lb_id, const std::string& sender_id, const std::string& receiver_id) {
  return lb_id + "|" + sender_id + "|" + receiver_id;
}

std::string key_receiver(const std::string& lb_id, const std::string& receiver_id) {
  return lb_id + "|" + receiver_id;
}

double now_unix() {
  using namespace std::chrono;
  auto n = system_clock::now().time_since_epoch();
  return duration_cast<duration<double>>(n).count();
}

void write_metrics_locked() {
  std::unordered_map<std::string, std::vector<std::tuple<std::string, std::string, StreamCounters>>> grouped;
  for (const auto& it : g_streams) {
    const std::string& k = it.first;
    const StreamCounters& c = it.second;
    size_t p1 = k.find('|');
    size_t p2 = k.find('|', p1 + 1);
    if (p1 == std::string::npos || p2 == std::string::npos) {
      continue;
    }
    std::string lb_id = k.substr(0, p1);
    std::string sender = k.substr(p1 + 1, p2 - p1 - 1);
    std::string receiver = k.substr(p2 + 1);
    grouped[lb_id].push_back({sender, receiver, c});
  }

  std::ostringstream os;
  os.setf(std::ios::fixed);
  os << std::setprecision(6);
  os << "{";
  os << "\"workers\":[";
  for (size_t i = 0; i < g_worker_counters.size(); ++i) {
    if (i > 0) {
      os << ",";
    }
    const WorkerCounters& wc = g_worker_counters[i];
    os << "{";
    os << "\"worker_id\":" << i << ",";
    os << "\"rx_datagrams\":" << wc.rx_datagrams << ",";
    os << "\"rx_datagram_bytes\":" << wc.rx_datagram_bytes << ",";
    os << "\"parse_errors\":" << wc.parse_errors << ",";
    os << "\"register_messages\":" << wc.register_messages << ",";
    os << "\"data_messages\":" << wc.data_messages << ",";
    os << "\"forwarded\":" << wc.forwarded << ",";
    os << "\"forwarded_bytes\":" << wc.forwarded_bytes << ",";
    os << "\"dropped\":" << wc.dropped << ",";
    os << "\"send_errors\":" << wc.send_errors;
    os << "}";
  }
  os << "],";

  bool first_lb = true;
  for (const auto& lb : grouped) {
    if (!first_lb) {
      os << ",";
    }
    first_lb = false;

    std::unordered_set<std::string> senders;
    std::unordered_set<std::string> receivers;
    for (const auto& stream : lb.second) {
      senders.insert(std::get<0>(stream));
      receivers.insert(std::get<1>(stream));
    }

    os << "\"" << json_escape(lb.first) << "\":{";
    os << "\"active_senders\":" << senders.size() << ",";
    os << "\"active_receivers\":" << receivers.size() << ",";
    os << "\"streams\":[";

    bool first_stream = true;
    for (const auto& stream : lb.second) {
      if (!first_stream) {
        os << ",";
      }
      first_stream = false;
      const std::string& sender = std::get<0>(stream);
      const std::string& receiver = std::get<1>(stream);
      const StreamCounters& c = std::get<2>(stream);
      double loss_pct = 0.0;
      if (c.tx_packets > 0) {
        loss_pct = (static_cast<double>(c.tx_packets - c.rx_packets) / static_cast<double>(c.tx_packets)) * 100.0;
        if (loss_pct < 0.0) {
          loss_pct = 0.0;
        }
      }
      os << "{";
      os << "\"sender_id\":\"" << json_escape(sender) << "\",";
      os << "\"receiver_id\":\"" << json_escape(receiver) << "\",";
      os << "\"tx_packets\":" << c.tx_packets << ",";
      os << "\"tx_bytes\":" << c.tx_bytes << ",";
      os << "\"rx_packets\":" << c.rx_packets << ",";
      os << "\"rx_bytes\":" << c.rx_bytes << ",";
      os << "\"dropped_packets\":" << c.dropped_packets << ",";
      os << "\"last_update_unix\":" << c.last_update_unix << ",";
      os << "\"packet_loss_pct\":" << loss_pct;
      os << "}";
    }
    os << "]}";
  }
  os << "}";

  std::ofstream out(metrics_file, std::ios::trunc);
  out << os.str();
}

void maybe_flush_metrics_locked(long stream_counter) {
  if ((stream_counter % 32) == 0) {
    write_metrics_locked();
    g_dirty.store(false, std::memory_order_release);
  } else {
    g_dirty.store(true, std::memory_order_release);
  }
}

void load_reservations() {
  std::ifstream in(reservations_file);
  if (!in.good()) {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_reservations.clear();
    return;
  }

  std::stringstream buf;
  buf << in.rdbuf();
  std::string raw = trim(buf.str());

  std::unordered_map<std::string, Reservation> next;

  size_t pos = 0;
  while (true) {
    pos = raw.find("\"lb_id\"", pos);
    if (pos == std::string::npos) {
      break;
    }

    size_t obj_start = raw.rfind('{', pos);
    size_t obj_end = raw.find('}', pos);
    if (obj_start == std::string::npos || obj_end == std::string::npos || obj_end <= obj_start) {
      break;
    }

    std::string obj = raw.substr(obj_start, obj_end - obj_start + 1);
    std::string lb_id;
    std::string token;
    if (extract_json_string(obj, "lb_id", &lb_id) && extract_json_string(obj, "token", &token)) {
      next[lb_id] = Reservation{token};
    }
    pos = obj_end + 1;
  }

  std::lock_guard<std::mutex> lock(g_mutex);
  g_reservations.swap(next);
}

void reservations_watcher() {
  while (g_running.load(std::memory_order_acquire)) {
    load_reservations();
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
  }
}

void metrics_flusher() {
  while (g_running.load(std::memory_order_acquire)) {
    std::this_thread::sleep_for(std::chrono::milliseconds(flush_interval_ms));
    if (!g_dirty.load(std::memory_order_acquire)) {
      continue;
    }
    std::lock_guard<std::mutex> lock(g_mutex);
    write_metrics_locked();
    g_dirty.store(false, std::memory_order_release);
  }
}

bool token_valid_locked(const std::string& lb_id, const std::string& token) {
  auto it = g_reservations.find(lb_id);
  if (it == g_reservations.end()) {
    return false;
  }
  return it->second.token == token;
}

void update_tx_locked(const Packet& pkt, long payload_bytes, long dropped) {
  StreamCounters& c = g_streams[key_stream(pkt.lb_id, pkt.sender_id, pkt.receiver_id)];
  c.tx_packets += 1;
  c.tx_bytes += payload_bytes;
  c.dropped_packets += dropped;
  c.last_update_unix = now_unix();
}

void update_rx_locked(const Packet& pkt, long payload_bytes) {
  StreamCounters& c = g_streams[key_stream(pkt.lb_id, pkt.sender_id, pkt.receiver_id)];
  c.rx_packets += 1;
  c.rx_bytes += payload_bytes;
  c.last_update_unix = now_unix();
}

void usage(const char* prog) {
  std::cerr << "Usage: " << prog
            << " --data-port <port> --reservations-file <path> --metrics-file <path>"
            << " [--drop-rate <0..1>] [--workers <n>] [--flush-interval-ms <n>]"
            << " [--pin-workers true|false] [--pin-base-cpu <n>]\n";
}

void process_datagram(
    int sock,
    const std::string& raw,
    const sockaddr_in& src,
  long datagram_bytes,
    int worker_id,
    std::mt19937& rng,
    std::uniform_real_distribution<double>& dist) {
  {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (worker_id >= 0 && static_cast<size_t>(worker_id) < g_worker_counters.size()) {
      g_worker_counters[static_cast<size_t>(worker_id)].rx_datagrams += 1;
      g_worker_counters[static_cast<size_t>(worker_id)].rx_datagram_bytes += datagram_bytes;
    }
  }

  Packet pkt;
  if (!parse_packet(raw, &pkt)) {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (worker_id >= 0 && static_cast<size_t>(worker_id) < g_worker_counters.size()) {
      g_worker_counters[static_cast<size_t>(worker_id)].parse_errors += 1;
      maybe_flush_metrics_locked(g_worker_counters[static_cast<size_t>(worker_id)].rx_datagrams);
    }
    return;
  }

  if (pkt.type == "register_receiver") {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (worker_id >= 0 && static_cast<size_t>(worker_id) < g_worker_counters.size()) {
      g_worker_counters[static_cast<size_t>(worker_id)].register_messages += 1;
    }
    if (token_valid_locked(pkt.lb_id, pkt.token) && !pkt.receiver_id.empty()) {
      g_receivers[key_receiver(pkt.lb_id, pkt.receiver_id)] = ReceiverAddr{src, true};
      g_dirty.store(true, std::memory_order_release);
    }
    return;
  }

  if (pkt.type != "packet") {
    return;
  }

  long payload_bytes = static_cast<long>(pkt.payload.size());

  sockaddr_in target{};
  bool should_forward = false;
  long tx_counter = 0;
  {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (worker_id >= 0 && static_cast<size_t>(worker_id) < g_worker_counters.size()) {
      g_worker_counters[static_cast<size_t>(worker_id)].data_messages += 1;
    }
    if (!token_valid_locked(pkt.lb_id, pkt.token)) {
      return;
    }

    long dropped = 0;
    const double r = dist(rng);
    if (r < drop_rate) {
      dropped = 1;
      if (worker_id >= 0 && static_cast<size_t>(worker_id) < g_worker_counters.size()) {
        g_worker_counters[static_cast<size_t>(worker_id)].dropped += 1;
      }
    }
    update_tx_locked(pkt, payload_bytes, dropped);

    StreamCounters& stream = g_streams[key_stream(pkt.lb_id, pkt.sender_id, pkt.receiver_id)];
    tx_counter = stream.tx_packets;
    maybe_flush_metrics_locked(tx_counter);

    if (dropped == 0) {
      auto it = g_receivers.find(key_receiver(pkt.lb_id, pkt.receiver_id));
      if (it != g_receivers.end() && it->second.valid) {
        target = it->second.addr;
        should_forward = true;
      }
    }
  }

  if (!should_forward) {
    return;
  }

  std::ostringstream out;
  out << "{";
  out << "\"type\":\"packet\",";
  out << "\"lb_id\":\"" << json_escape(pkt.lb_id) << "\",";
  out << "\"sender_id\":\"" << json_escape(pkt.sender_id) << "\",";
  out << "\"receiver_id\":\"" << json_escape(pkt.receiver_id) << "\",";
  out << "\"seq\":" << pkt.seq << ",";
  out << "\"payload\":\"" << json_escape(pkt.payload) << "\"";
  out << "}";
  const std::string payload = out.str();

  ssize_t sent = sendto(sock, payload.data(), payload.size(), 0, reinterpret_cast<const sockaddr*>(&target), sizeof(target));
  if (sent <= 0) {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (worker_id >= 0 && static_cast<size_t>(worker_id) < g_worker_counters.size()) {
      g_worker_counters[static_cast<size_t>(worker_id)].send_errors += 1;
      maybe_flush_metrics_locked(g_worker_counters[static_cast<size_t>(worker_id)].rx_datagrams);
    }
    return;
  }

  {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (worker_id >= 0 && static_cast<size_t>(worker_id) < g_worker_counters.size()) {
      g_worker_counters[static_cast<size_t>(worker_id)].forwarded += 1;
      g_worker_counters[static_cast<size_t>(worker_id)].forwarded_bytes += static_cast<long>(sent);
    }
    update_rx_locked(pkt, payload_bytes);
    StreamCounters& stream = g_streams[key_stream(pkt.lb_id, pkt.sender_id, pkt.receiver_id)];
    maybe_flush_metrics_locked(stream.rx_packets);
  }
}

int make_bound_socket(int port) {
  int sock = socket(AF_INET, SOCK_DGRAM, 0);
  if (sock < 0) {
    return -1;
  }

  int reuse_addr = 1;
  if (setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &reuse_addr, sizeof(reuse_addr)) < 0) {
    close(sock);
    return -1;
  }

  sockaddr_in bind_addr{};
  bind_addr.sin_family = AF_INET;
  bind_addr.sin_port = htons(static_cast<uint16_t>(port));
  bind_addr.sin_addr.s_addr = htonl(INADDR_ANY);

  if (bind(sock, reinterpret_cast<sockaddr*>(&bind_addr), sizeof(bind_addr)) < 0) {
    close(sock);
    return -1;
  }

  return sock;
}

void worker_loop(int sock, int worker_id) {
#ifdef __linux__
  if (pin_workers) {
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    int cpu = pin_base_cpu + worker_id;
    if (cpu < 0) {
      cpu = worker_id;
    }
    CPU_SET(cpu, &cpuset);
    pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);
  }
#else
  (void)worker_id;
#endif

  std::mt19937 rng(static_cast<unsigned int>(std::time(nullptr)) + static_cast<unsigned int>(worker_id * 2654435761U));
  std::uniform_real_distribution<double> dist(0.0, 1.0);

  while (g_running.load(std::memory_order_acquire)) {
    Datagram d;
    {
      std::unique_lock<std::mutex> lock(*g_worker_queue_mutexes[static_cast<size_t>(worker_id)]);
      g_worker_queue_cvs[static_cast<size_t>(worker_id)]->wait(lock, [worker_id] {
        return !g_running.load(std::memory_order_acquire) || !g_worker_queues[static_cast<size_t>(worker_id)].empty();
      });
      if (!g_running.load(std::memory_order_acquire)) {
        return;
      }
      d = std::move(g_worker_queues[static_cast<size_t>(worker_id)].front());
      g_worker_queues[static_cast<size_t>(worker_id)].pop_front();
    }

    process_datagram(sock, d.raw, d.src, d.byte_len, worker_id, rng, dist);
  }
}

void ingest_loop(int sock) {
  constexpr size_t kBufSize = 65536;
  std::vector<char> buffer(kBufSize);

  while (g_running.load(std::memory_order_acquire)) {
    sockaddr_in src{};
    socklen_t src_len = sizeof(src);
    ssize_t n = recvfrom(sock, buffer.data(), buffer.size(), 0, reinterpret_cast<sockaddr*>(&src), &src_len);
    if (n <= 0) {
      if (errno == EINTR) {
        continue;
      }
      continue;
    }

    Datagram d;
    d.src = src;
    d.raw.assign(buffer.data(), static_cast<size_t>(n));
    d.byte_len = static_cast<long>(n);

    size_t target = static_cast<size_t>(g_dispatch_rr.fetch_add(1, std::memory_order_relaxed) % static_cast<unsigned long long>(workers));
    {
      std::lock_guard<std::mutex> lock(*g_worker_queue_mutexes[target]);
      g_worker_queues[target].push_back(std::move(d));
    }
    g_worker_queue_cvs[target]->notify_one();
  }
}

}  // namespace

int main(int argc, char** argv) {
  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if (arg == "--data-port" && i + 1 < argc) {
      data_port = std::stoi(argv[++i]);
      continue;
    }
    if (arg == "--reservations-file" && i + 1 < argc) {
      reservations_file = argv[++i];
      continue;
    }
    if (arg == "--metrics-file" && i + 1 < argc) {
      metrics_file = argv[++i];
      continue;
    }
    if (arg == "--drop-rate" && i + 1 < argc) {
      drop_rate = std::stod(argv[++i]);
      if (drop_rate < 0.0) {
        drop_rate = 0.0;
      }
      if (drop_rate > 1.0) {
        drop_rate = 1.0;
      }
      continue;
    }
    if (arg == "--workers" && i + 1 < argc) {
      workers = std::stoi(argv[++i]);
      if (workers < 1) {
        workers = 1;
      }
      continue;
    }
    if (arg == "--flush-interval-ms" && i + 1 < argc) {
      flush_interval_ms = std::stoi(argv[++i]);
      if (flush_interval_ms < 10) {
        flush_interval_ms = 10;
      }
      continue;
    }
    if (arg == "--pin-workers" && i + 1 < argc) {
      const std::string val = argv[++i];
      pin_workers = (val == "1" || val == "true" || val == "TRUE" || val == "yes" || val == "on");
      continue;
    }
    if (arg == "--pin-base-cpu" && i + 1 < argc) {
      pin_base_cpu = std::stoi(argv[++i]);
      continue;
    }
    usage(argv[0]);
    return 2;
  }

  if (reservations_file.empty() || metrics_file.empty()) {
    usage(argv[0]);
    return 2;
  }

  {
    std::ofstream out(metrics_file, std::ios::trunc);
    out << "{}";
  }

  std::thread watcher(reservations_watcher);
  watcher.detach();
  std::thread flusher(metrics_flusher);
  flusher.detach();

  std::vector<int> sockets;
  sockets.reserve(1);
  {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_worker_counters.clear();
    g_worker_counters.resize(static_cast<size_t>(workers));
  }
  g_worker_queues.clear();
  g_worker_queue_mutexes.clear();
  g_worker_queue_cvs.clear();
  g_worker_queues.resize(static_cast<size_t>(workers));
  g_worker_queue_mutexes.reserve(static_cast<size_t>(workers));
  g_worker_queue_cvs.reserve(static_cast<size_t>(workers));
  for (int i = 0; i < workers; ++i) {
    g_worker_queue_mutexes.push_back(std::make_unique<std::mutex>());
    g_worker_queue_cvs.push_back(std::make_unique<std::condition_variable>());
  }

  int sock = make_bound_socket(data_port);
  if (sock < 0) {
    std::perror("bind");
    return 1;
  }
  sockets.push_back(sock);

  if (sockets.empty()) {
    std::cerr << "No worker sockets were created\n";
    return 1;
  }

  std::vector<std::thread> worker_threads;
  worker_threads.reserve(static_cast<size_t>(workers));
  for (int i = 0; i < workers; ++i) {
    worker_threads.emplace_back(worker_loop, sock, i);
  }

  std::thread ingest(ingest_loop, sock);
  ingest.join();

  for (auto& t : worker_threads) {
    t.join();
  }

  for (int sock : sockets) {
    close(sock);
  }

  return 0;
}
