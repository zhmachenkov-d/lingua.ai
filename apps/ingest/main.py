from ingest.spike.measure import run_spike

if __name__ == "__main__":
    result = run_spike()
    print(
        f"spike done: note={result.note_path} "
        f"measured={result.measured_count} failed={result.failed_count} "
        f"peak_rss_mib={result.job_peak_rss_mb:.1f}"
    )
