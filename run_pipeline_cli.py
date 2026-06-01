from pathlib import Path
import sys
from src.topic_input import load_topic_request
from src.pipeline import run_pipeline

def main():
    topic_json_path = Path("input/topic.json")
    if not topic_json_path.exists():
        print("Error: input/topic.json not found.")
        sys.exit(1)

    req = load_topic_request(topic_json_path)
    print(f"Topic: {req.topic}")
    print(f"Official URL: {req.official_url}")
    print(f"Output Suffix: {req.output_suffix}")

    config_path = Path("config.yaml")
    
    print("Running pipeline...")
    result = run_pipeline(
        topic=req.topic,
        official_url=req.official_url,
        config_path=config_path,
        output_suffix=req.output_suffix
    )
    print("Pipeline finished successfully!")
    print(f"Output Directory: {result['output_dir']}")
    print("Files generated:")
    for key, path in result['files'].items():
        print(f"  {key}: {path}")

if __name__ == "__main__":
    main()
