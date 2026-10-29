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

DATE_HUMAN="$(date -u +"%Y/%m/%d")"
cat > humans.txt <<EOF
/* TEAM */
Your title: CILT - LT Team
Site: http://www.cilt.uct.ac.za/
Repo: https://$GITHUB
Location: Cape Town, South Africa

/* THANKS */
Name: Opencast (https://github.com/opencast/)

/* SITE */
Last update: $DATE_HUMAN
Version: $VERSION_TAG
Standards: HTML5, CSS3
Components: FastAPI
Software: Shows the status of all the cameras, capture agents and todays schedule sourced from Opencast

/* https://humanstxt.org/ */
EOF
git add humans.txt

if [[ "$user" != "NA" ]]; then
    git commit --author="$user" -m "$msg"
else
    git commit -m "$msg"
fi

case $yn in
    [Yy]* ) bash push.sh;;
esac
