#!/usr/bin/env python3
import logging
import os
import sys
import subprocess

logging.basicConfig(filename="/home/pi/Downloads/sonarr-import.log",
                    format="%(asctime)s %(levelname)-8s %(message)s",
                    level=logging.INFO,
                    datefmt='%Y-%m-%d %H:%M:%S')

logging.info("Sonarr extra script post processing started.")

if os.environ.get('sonarr_eventtype') == "Test":
    logging.info("Successful sonarr-import.py SMA test, exiting.")
    sys.exit(0)

if os.environ.get('sonarr_eventtype') != "Download":
    logging.error(f"Invalid event type: {os.environ.get('sonarr_eventtype')}, script only works for On Download/On Import and On Upgrade.")
    sys.exit(1)

try:
    input_file = os.environ.get('sonarr_episodefile_path')
    release_group = os.environ.get('sonarr_episodefile_quality')
except Exception as error:
    logging.error(f"Error reading environment variables {str(error)}")
    sys.exit(1)
try:
    file_components = os.path.splitext(input_file)
    file_extension = file_components[-1]
    file_root = file_components[0]
except Exception as error:
    logging.error(f"Error getting file extension {str(error)}")
    sys.exit(1)

if "720" in release_group:
    target_bitrate = 2.5
    conversion_bitrate = 1
elif "1080" in release_group:
    target_bitrate = 3.5
    conversion_bitrate = 2
else:
    logging.info("Unrecognized quality exiting")
    sys.exit(0)

status, output = subprocess.getstatusoutput(f"ls -s \"{input_file}\"")

if status != 0:
    logging.error(f"Error reading file size {output}")
    sys.exit(status)

try:
    file_size = float(output.split(' ')[0])
except ValueError as error:
    logging.error(f"Error reading file size. {str(error)}")
    sys.exit(1)

status, output = subprocess.getstatusoutput(f"ffprobe -v error -show_entries format=duration:stream=index -of default=noprint_wrappers=1:nokey=1 \"{input_file}\"")
if status != 0:
    logging.error(f"Error reading video duration: {output}")
    sys.exit(status)

duration = 0
for line in output.split("\n"):
    try:
        streamDuration = float(line)
        if streamDuration > duration:
            duration = streamDuration
    except ValueError:
        continue

if duration == 0:
    logging.error(f"Error reading video duration")
    sys.exit(1)

bitrate = 8 * file_size / duration

# Re-encode the video if the bitrate is too high
if (bitrate / 1000) > target_bitrate:
    logging.info(f"Converting {input_file} from {bitrate/1000}Mb/s -> {conversion_bitrate}Mb/s")
    status, output = subprocess.getstatusoutput("atq | wc -l")
    tasks_in_queue = int(output)
    logging.info(f"{tasks_in_queue} conversion tasks already in queue")

    first_pass = f"ffmpeg -y -i \"{input_file}\" -c:v libx264 -b:v {conversion_bitrate}M -pass 1 -vsync cfr -passlogfile /tmp/dummy_log -f null /dev/null"
    second_pass = f"ffmpeg -i \"{input_file}\" -c:v libx264 -b:v {conversion_bitrate}M -pass 2 -passlogfile /tmp/dummy_log \"{file_root}_converted{file_extension}\""
    conversion_command = f"{first_pass} && {second_pass} && rm \"{input_file}\" && mv \"{file_root}_converted{file_extension}\" \"{input_file}\""
    schedule_command = "at 23:00"
    if tasks_in_queue > 0:
        schedule_command = f"at 23:00 + {tasks_in_queue} days"
    
    full_command = f"echo '{conversion_command}' | {schedule_command}"
    logging.info(f"Running command: {full_command}")
    subprocess.run(full_command, shell=True)
