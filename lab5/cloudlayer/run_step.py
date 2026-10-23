"""Map platform-specific job context into the neutral pipeline process."""
import os

from src.pipeline_steps import main

if __name__ == "__main__":
    os.environ["LAB5_TRAINING_JOB_ID"] = os.environ.get("AZUREML_RUN_ID", "")
    main()
