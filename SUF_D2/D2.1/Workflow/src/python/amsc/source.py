
import argparse
import time
import signal
import sys
import pandas
import os
import pickle
import zmq

from amsc import hddm_reader,credentials,ejfat,message


def add_arguments(parser):
    parser.add_argument("input_filename", help="Input REST filename")
    parser.add_argument("--credential-dir", default=credentials.default_credential_dir, help="Directory for sharing ZMQ and EJFAT credentials")
    parser.add_argument("--name", default="source0", help="Name for this source")
    parser.add_argument("--loop", action=argparse.BooleanOptionalAction, default=True, help="Loop input file for infinite stream")
    parser.add_argument("--include-tables", help="Comma-separated list of tables (HDDM tags) to include")
    parser.add_argument("--input-port", type=int, default=12543, help="Port for EJFAT to stream data back to")
    parser.add_argument("--monitor-zmq-uri", default="tcp://127.0.0.1:5557", help="ZMQ PUSH target for monitor process")
    parser.add_argument("--stats-every", type=float, default=1.0, help="Print one stats line every n seconds")
    parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Print full message content")
    parser.add_argument("--batch-size", type=int, default=1, help="Physics events per message")
    parser.add_argument("--max-event-rate", type=float, default=1.0, help="Max (physics) event rate [Hz]")
    parser.add_argument("--preload", action=argparse.BooleanOptionalAction, default=True, help="Load all data before starting streaming, to achieve higher event rates")
    parser.add_argument("--preload-count", type=int, default=-1, help="Number of messages to preload. -1 denotes all events")


def run(args):

    print("Running EJFAT source:")
    print("  input_filename: ", args.input_filename)
    print("  credential_dir: ", args.credential_dir)
    print("  name:           ", args.name)
    print("  batch_size:     ", args.batch_size)
    print("  loop:           ", args.loop)
    print("  include_tables: ", args.include_tables)
    print("  input_port:     ", args.input_port)
    print("  monitor_zmq_uri:", args.monitor_zmq_uri)
    print("  stats_every:    ", args.stats_every)
    print("  max_event_rate: ", args.max_event_rate)
    print("  preload:        ", args.preload)
    print("  preload_count:  ", args.preload_count)
    print("  verbose:        ", args.verbose)
    print()


    ejfat_uri_raw = credentials.get_ejfat_uri_raw(args.credential_dir)
    ejfat_uri_processed = credentials.get_ejfat_uri_processed(args.credential_dir)
    print("Acquired credentials:")
    print("  ejfat_uri_raw:        ", ejfat_uri_raw)

    print("  ejfat_uri_processed:  ", ejfat_uri_processed)
    print()

    ejfat_sender = ejfat.EjfatSender(ejfat_uri_raw)
    ejfat_sender.connect()

    ejfat_receiver = ejfat.EjfatReceiver("source", ejfat_uri_processed, args.input_port)
    ejfat_receiver.connect()

    # ZMQ link to monitoring process
    zmq_ctx = zmq.Context.instance()
    monitor_sock = zmq_ctx.socket(zmq.PUSH)
    monitor_sock.connect(args.monitor_zmq_uri)
    print("Connected monitor ZMQ PUSH:", args.monitor_zmq_uri)

    # Fire up the HDDM reader
    reader = hddm_reader.HDDMReader(args.input_filename, args.batch_size, args.loop)

    if args.preload:
        print("Preloading all data...")
        preloaded = []
        msg_nr = 0
        while True:
            msg = reader.read_batch()
            msg_nr += 1

            if msg is None:
                break

            preloaded.append(msg)
            if msg_nr >= args.preload_count:
                break

        print("Successfully preloaded all data...")

    # Loop until killed
    running = True
    def shutdown(signum, frame):
        nonlocal running
        running = False
        print("\nShutdown requested...")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    event_nr = 0
    sent_raw_count = 0
    recv_processed_count = 0
    forwarded_count = 0
    decode_failures = 0
    monitor_send_failures = 0
    stats_every = max(1, int(args.stats_every))
    t0 = time.monotonic()

    while running:
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
            print(f"Sending raw payload: evt_nr={evt_nr}")
        ejfat_sender.send(data, event_nr)
        sent_raw_count += 1

        # Quickly check if we've received something
        evt_length, evt_bytes, evt_nr, data_id = ejfat_receiver.recv(1)
        if evt_length >= 0:
            recv_processed_count += 1
            if args.verbose:
                print(f"Received processed payload: evt_nr={evt_nr} src={data_id} bytes={evt_length}")

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
            proc_rate = recv_processed_count / dt
            mon_rate = forwarded_count / dt
            print(
                "source "
                f"raw_sent={sent_raw_count} ({raw_rate:.1f}/s) "
                f"processed_recv={recv_processed_count} ({proc_rate:.1f}/s) "
                f"monitor_fwd={forwarded_count} ({mon_rate:.1f}/s) "
                f"decode_fail={decode_failures} monitor_send_fail={monitor_send_failures}"
            )
            t0 = t2
            sent_raw_count = 0
            recv_processed_count = 0
            forwarded_count = 0

        delay = max(args.batch_size/args.max_event_rate - (t2-t1), 0)
        time.sleep(delay) # seconds
        event_nr += 1


    ejfat_sender.disconnect()
    ejfat_receiver.disconnect()
    monitor_sock.close()
    zmq_ctx.term()



