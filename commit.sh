#! /bin/bash

source base.sh

bash check.sh
ret=$?
if [ $ret -ne 0 ]; then
    echo
    git status
    exit 0
fi

read -p "[$branch_name] Commit: " msg
read -p "Push [Y/n]: " yn
yn=${yn:-'Y'}

if [[ "$user" != "NA" ]]; then
    git commit --author="$user" -m "$msg"
else
    git commit -m "$msg"
fi

case $yn in
    [Yy]* ) bash push.sh;;
esac
