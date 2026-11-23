"""Application payload rates, using decimal MB and Mbit units."""


def format_payload_rate(name, byte_count, elapsed_seconds):
    mb_per_sec = byte_count / elapsed_seconds / 1_000_000
    return f"{name}={mb_per_sec:.3f} MB/s ({mb_per_sec * 8:.3f} Mbit/s)"
