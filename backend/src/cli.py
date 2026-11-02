import argparse

from src.jobCreators.fileModule import FileModule
from src.jobProcessor import JobProcessor


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--folder",
        required=True,
        help="Folder containing session files",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    entrypoint = FileModule(supported_files=[".tcx", ".fit"], meta_extension=".json")
    jobs = entrypoint.extract_folder(folder_path=args.folder)

    processor = JobProcessor()

    for job in jobs:
        processor.process_job(job)


if __name__ == "__main__":
    main()
