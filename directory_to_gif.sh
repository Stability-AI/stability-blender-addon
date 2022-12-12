#!/bin/bash

# Convert a directory of images to GIFs.
# Usage: directory_to_gif.sh directory_name output_name.gif

# Get the directory name and output name from the command line.
directory=$1

SCALE=480

echo "Converting $directory to $output"

for file in "$1"/* ;do
    [ -f "$file" ] && echo "Process '$file'."
    # skip non mp4 files
    if [[ $file == *.mp4 ]]; then
        # get the filename without the extension
        filename=$(basename -- "$file")
        filename="${filename%.*}"
        # convert the mp4 to a gif
        ffmpeg -y -i "$file" -vf "fps=10,scale=$SCALE:-1:flags=lanczos,palettegen" "$directory/$filename.png"
        ffmpeg -y -i "$file" -i "$directory/$filename.png" -filter_complex "fps=10,scale=$SCALE:-1:flags=lanczos[x];[x][1:v]paletteuse" "$directory/$filename.gif"
    fi
    # base_name=$(basename "$file")
    # base="${base_name%.*}"
    # echo "Converting $file $base_name $base to gif"
    # ffmpeg -i $file -vf "fps=10,scale=320:-1:flags=lanczos" -c:v pam \
    # -f image2pipe - | \
    # convert -delay 10 - -loop 0 -layers optimize output.gif
done
