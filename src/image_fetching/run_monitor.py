#!/usr/bin/env python3
import asyncio
import json
import sys
from pathlib import Path

# Import from same directory
from camera_image_decoder import CameraImageFetcher

# Force unbuffered output
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

async def run_monitoring():
    config_path = Path(__file__).parent / 'monitor_config.json'
    with open(config_path) as f:
        config = json.load(f)
    
    # Create logs directory
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    fetcher = CameraImageFetcher(verbose=True)
    
    print("🚀 Starting monitoring...")
    print(f"📁 Output base: {config['output_base']}")
    print(f"⏰ Interval: {config['interval']}, Duration: {config['duration']}")
    
    # Run all camera groups concurrently
    tasks = []
    for location, camera_ids in config["cameras"].items():
        output_dir = f"{config['output_base']}/{location}"
        print(f"📹 {location}: cameras {camera_ids} -> {output_dir}")
        task = fetcher.monitor_async(
            camera_ids,
            config["interval"], 
            config["duration"], 
            output_dir
        )
        tasks.append(task)
    
    print("🔄 Starting concurrent monitoring...")
    await asyncio.gather(*tasks)
    await fetcher._close_session()
    print("✅ Monitoring completed!")

if __name__ == "__main__":
    asyncio.run(run_monitoring())