#! /bin/bash

source base.sh

read -p "Branch [$branch_name]: " branch
branch=${branch:-$branch_name}

read -p "Github Username (not email): " username
read -p "Force push? (y/N): " force_push
force_flag=""
if [[ "$force_push" =~ ^[Yy]$ ]]; then
  force_flag="--force"
fi

git push $force_flag https://$username@$GITHUB $branch

if [ $? -eq 0 ]; then
  bash $SCRIPT_FOLDER/get.sh
fi
