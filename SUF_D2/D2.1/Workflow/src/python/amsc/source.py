
import argparse
import time
import signal
import sys
import pandas
import os
import pickle
import zmq
import multiprocessing as mp

from amsc import hddm_reader,credentials,ejfat,message


def add_arguments(parser):
    parser.add_argument("input_filename", help="Input REST filename")
    parser.add_argument("--parallelism", type=int, default=1, help="Number of parallel processes to launch on this node")
    parser.add_argument("--credential-dir", default=credentials.default_credential_dir, help="Directory for sharing ZMQ and EJFAT credentials")
    parser.add_argument("--loop", action=argparse.BooleanOptionalAction, default=True, help="Loop input file for infinite stream")
    parser.add_argument("--include-tables", help="Comma-separated list of tables (HDDM tags) to include")
    parser.add_argument("--input-port", type=int, default=19900, help="Port for EJFAT to stream data back to. If no port is specified, uses 19700+id")
    parser.add_argument("--monitor-zmq-uri", default="tcp://127.0.0.1:5557", help="ZMQ PUSH target for monitor process")
    parser.add_argument("--stats-every", type=float, default=3.0, help="Print one stats line every n seconds")
    parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Print full message content")
    parser.add_argument("--batch-size", type=int, default=1, help="Physics events per message")
    parser.add_argument("--max-event-rate", type=float, default=None, help="Max (physics) event rate [Hz]")
    parser.add_argument("--preload", action=argparse.BooleanOptionalAction, default=True, help="Preload data before starting streaming, to achieve higher event rates")
    parser.add_argument("--preload-count", type=int, default=1, help="Number of batches to preload. -1 denotes all batches")
    parser.add_argument("--mtu", type=int, default=1500, help="Max transmission unit (set to 9000 when the network supports it)")
    parser.add_argument("--ip", type=str, default=None, help="IP address to register with LB (defaults to autoip)")


ZMQ_URI_RATES = "tcp://127.0.0.1:5551"
ZMQ_URI_CONTROL = "tcp://127.0.0.1:5552"   # PUB/SUB for broadcast shutdown

def run_source(id, args):

    signal.signal(signal.SIGINT, signal.SIG_IGN)

    ejfat_uri_raw = credentials.get_ejfat_uri_raw(args.credential_dir)
    ejfat_uri_processed = credentials.get_ejfat_uri_processed(args.credential_dir)
    print("Acquired credentials:")
    print("  ejfat_uri_raw:        ", ejfat_uri_raw)

    print("  ejfat_uri_processed:  ", ejfat_uri_processed)
    print()

    ejfat_sender = ejfat.EjfatSender(ejfat_uri_raw, id, args.mtu, args.ip)
    ejfat_sender.connect()

    ejfat_receiver = ejfat.EjfatReceiver(f"source_receiver{id}", ejfat_uri_processed, args.ip, args.input_port+id)
    ejfat_receiver.connect()

    # ZMQ link to supervisor
    zmq_ctx = zmq.Context.instance()
    rates_socket = zmq_ctx.socket(zmq.PUSH)
    rates_socket.setsockopt(zmq.LINGER, 0) # Discard any unsent messages on shutdown
    rates_socket.connect(ZMQ_URI_RATES)        # supervisor binds, workers connect

    ctrl_socket = zmq_ctx.socket(zmq.SUB)
    ctrl_socket.connect(ZMQ_URI_CONTROL)
    ctrl_socket.setsockopt_string(zmq.SUBSCRIBE, "")   # subscribe to all messages

    poller = zmq.Poller()
    poller.register(ctrl_socket, zmq.POLLIN)   # only need to poll control channel;



    # ZMQ link to monitoring process
    monitor_sock = zmq_ctx.socket(zmq.PUSH)
    monitor_sock.setsockopt(zmq.LINGER, 0) # Discard any unsent messages on shutdown
    monitor_sock.connect(args.monitor_zmq_uri)
    print("Connected monitor ZMQ PUSH:", args.monitor_zmq_uri)

    # Fire up the HDDM reader
    reader = hddm_reader.HDDMReader(args.input_filename, args.batch_size, args.loop)

    if args.preload:
        print(f"Preloading {args.preload_count} batches...")
        preloaded = []
        msg_nr = 0
        while True:
            msg = reader.read_batch()
            msg_nr += 1

            if msg is None:
                break

            preloaded.append(msg)
            if (msg_nr >= args.preload_count) and (args.preload_count > 0):
                break

        print("... Finished preloading data")

    event_nr = 0
    sent_raw_count = 0
    sent_raw_bytes = 0
    recv_processed_count = 0
    forwarded_count = 0
    decode_failures = 0
    monitor_send_failures = 0
    stats_every = max(1, int(args.stats_every))
    t0 = time.monotonic()

    while True:
        t1 = time.monotonic()

        if args.preload:
            if args.loop:
                msg = preloaded[event_nr % len(preloaded)]
            else:
                if event_nr >= len(preloaded):
                    break
                msg=preloaded[event_nr]
        else:
            # Not preloaded
            msg = reader.read_batch()
            if not msg:
                break

        if args.verbose:
            msg.print_selected(args.include_tables)
        #elif event_nr % stats_every == 0:
        #    msg.print_short()

        # Convert message to bytes
        data = msg.to_arrow()

        # Send message
        if args.verbose:
            print(f"Sending raw data batch {event_nr} of size {len(data)}")
        ejfat_sender.send(data, event_nr)
        sent_raw_count += 1
        sent_raw_bytes += len(data)

        # Receive ZMQ shutdown message (nonblocking)
        if poller.poll(0):
            msg = ctrl_socket.recv_string()
            if msg == "stop":
                print(f"Source {id}: Received shutdown message")
                break

        # Quickly check if we've received something
        evt_length, evt_bytes, evt_nr, data_id = ejfat_receiver.recv(1)
        if evt_length >= 0:
            recv_processed_count += 1
            if args.verbose:
                print(f"Received processed batch: evt_nr={evt_nr} src={data_id} bytes={evt_length}")

            # Deserialize Arrow bytes once here, then send compact DataFrame dict to monitor.
            try:
                processed_msg = message.Message.from_arrow(evt_bytes)
                processed_tables = {
                    table_name: processed_msg[table_name]
                    for table_name in processed_msg.keys()
                }
            except Exception as exc:
                decode_failures += 1
                print(f"Warning: failed to decode processed payload ({decode_failures} errors): {exc}")
                print(evt_bytes)
                processed_tables = None

            if processed_tables is not None:
                try:
                    payload = pickle.dumps(processed_tables, protocol=pickle.HIGHEST_PROTOCOL)
                    monitor_sock.send(payload)
                    forwarded_count += 1
                    if args.verbose and forwarded_count % stats_every == 0:
                        print(f"Forwarded {forwarded_count} processed messages to monitor")
                except Exception as exc:
                    monitor_send_failures += 1
                    print(f"Warning: failed to send to monitor ({monitor_send_failures} errors): {exc}")


        t2 = time.monotonic()
        dt = t2 - t0
        if dt > args.stats_every:
            raw_rate = sent_raw_count / dt
            raw_mb_s = sent_raw_bytes / dt / 1_000_000
            proc_rate = recv_processed_count / dt
            mon_rate = forwarded_count / dt
            print(
                f"Source {id}: "
                f"raw_sent={sent_raw_count} ({raw_rate:.1f}/s) "
                f"processed_recv={recv_processed_count} ({proc_rate:.1f}/s) "
                f"monitor_fwd={forwarded_count} ({mon_rate:.1f}/s) "
                f"decode_fail={decode_failures} monitor_send_fail={monitor_send_failures}"
            )
            rates_socket.send_pyobj({"id": id, "raw_mb_s": raw_mb_s})
            t0 = t2
            sent_raw_count = 0
            sent_raw_bytes = 0
            recv_processed_count = 0
            forwarded_count = 0

        if args.max_event_rate is not None:
            delay = max(args.batch_size/args.max_event_rate - (t2-t1), 0)
            time.sleep(delay) # seconds
        event_nr += 1


    ejfat_sender.disconnect()
    ejfat_receiver.disconnect()

    print("Closing ZMQ sockets...")
    ctrl_socket.close()
    rates_socket.close()
    monitor_sock.close()
    zmq_ctx.term()



def run(args):

    print("Running EJFAT source:")
    print("  input_filename: ", args.input_filename)
    print("  parallelism:    ", args.parallelism)
    print("  credential_dir: ", args.credential_dir)
    print("  batch_size:     ", args.batch_size)
    print("  loop:           ", args.loop)
    print("  include_tables: ", args.include_tables)
    print("  input_port:     ", args.input_port)
    print("  monitor_zmq_uri:", args.monitor_zmq_uri)
    print("  stats_every:    ", args.stats_every)
    print("  max_event_rate: ", args.max_event_rate)
    print("  preload:        ", args.preload)
    print("  preload_count:  ", args.preload_count)
    print("  mtu:            ", args.mtu)
    print("  verbose:        ", args.verbose)
    print()

    ctx  = zmq.Context()

    rates_socket = ctx.socket(zmq.PULL)
    rates_socket.bind(ZMQ_URI_RATES)

    ctrl_socket = ctx.socket(zmq.PUB)
    ctrl_socket.bind(ZMQ_URI_CONTROL)

    workers = [mp.Process(target=run_source, args=(i, args))
                  for i in range(args.parallelism)]

    for w in workers:
        w.start()

    def shutdown(signum, frame):
        print("\nTelling sources to shut down ...")
        ctrl_socket.send_string("stop")        # broadcast to all workers at once
        print("Joining workers...")
        for w in workers:
            w.join()
        print("Done joining workers.")
        rates_socket.close()
        ctrl_socket.close()
        ctx.term()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)

    source_rates = {}
    while True:
        msg = rates_socket.recv_pyobj()         # blocks until any source sends
        source_rates[msg["id"]] = msg["raw_mb_s"]
        if len(source_rates) == args.parallelism:
            total_mb_s = sum(source_rates.values())
            print(
                f"All sources ({args.parallelism}): "
                f"raw_tx_offered={total_mb_s:.3f} MB/s ({total_mb_s * 8:.3f} Mbit/s)"
            )
            source_rates.clear()

