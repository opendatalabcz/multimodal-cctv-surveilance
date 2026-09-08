from __future__ import annotations

import asyncio
import json
import sys
from importlib.resources import files

from cctv.fetch.decoder import CameraImageFetcher
from cctv.utils.paths import data_root, logs_dir


async def run_monitoring() -> None:
    config = json.loads(files("cctv.fetch").joinpath("monitor_config.json").read_text(encoding="utf-8"))
    logs_dir().mkdir(parents=True, exist_ok=True)

    output_base = data_root() / config["output_base"]
    fetcher = CameraImageFetcher(verbose=True)

    print("Starting monitoring...")
    print(f"Output base: {output_base}")
    print(f"Interval: {config['interval']}, Duration: {config['duration']}")

    tasks = []
    for location, camera_ids in config["cameras"].items():
        output_dir = output_base / location
        print(f"{location}: cameras {camera_ids} -> {output_dir}")
        tasks.append(
            fetcher.monitor_async(
                camera_ids,
                config["interval"],
                config["duration"],
                str(output_dir),
            )
        )

    print("Starting concurrent monitoring...")
    await asyncio.gather(*tasks)
    await fetcher._close_session()
    print("Monitoring completed!")


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    asyncio.run(run_monitoring())


if __name__ == "__main__":
    main()
