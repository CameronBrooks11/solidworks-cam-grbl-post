# Check the post's source, render a job from it and test the G-code checker
test:
    python3 tests/test_post.py

# Check a posted file: just check-nc grblhal part.nc
check-nc controller +files:
    python3 tools/check_gcode.py --controller {{controller}} {{files}}

# Draw the README pictures into images/
images:
    python3 tools/draw_start.py images/start_of_job.svg
    python3 tools/draw_sample.py images/sample_job.svg
