What fired: Scheduled PSI detector; threshold 0.76223; alert accepted after 521.91 seconds.
True cause: The controlled input replay added 12 C to temp_c; this simulates an upstream calibration error.
Retrain, roll back, or no action — and why: Restore the input producer and replay an unshifted window; keep the model, because retraining on corrupted temperatures would learn the error.
What this would have cost if unnoticed for a week: Incorrect maintenance decisions and repeated alerts; monetary impact is unmeasured and needs request volume, decision costs, and billing data.
How to prevent or detect it faster: Validate sensor calibration and units at ingestion; keep the five-minute schedule and measure Log Analytics ingestion and job startup delay separately.
