#! /bin/bash

# Function to print usage instructions
function usage {
  echo ""
  echo "Usage: $0 [--patch|--minor|--major] | [-h]"
  echo ""
  echo "Should this be a patch/minor/major release."
  echo "To pull the command out of your last git commit, you can add [bump major] or [bump minor] to your git commit."
  echo ""
  echo "Options:"
  echo "  --patch     Patch release - increment x.x.N"
  echo "  --minor     Minor release - increment x.N.x"
  echo "  --major     Major release - increment N.x.x"
  exit 1
}

ACTION="$(git log -1 --pretty=%B)"

# Parse command line arguments
while [ "$1" != "" ]; do
    case $1 in
        --patch )     shift
                      ACTION="--patch"
                      ;;
        --minor )     shift
                      ACTION="--minor"
                      ;;
        --major )     shift
                      ACTION="--major"
                      ;;
        -h | --help ) usage
                      exit
                      ;;
        * )           shift
                      ;;
    esac
    shift
done

source base.sh

# ensure we're up to date
./get.sh

# bump version - update VERSION
./gitbump.sh $ACTION

version=$(tr -d ' \n\r\t' < VERSION)

# tag it
git add -A

msg="Version v$version"
if [[ "$user" != "NA" ]]; then
    git commit --author="$user" -m "$msg"
else
    git commit -m "$msg"
fi

git tag -a "v$version" -m "Version v$version"

read -p "Branch [$branch_name]: " branch
branch=${branch:-$branch_name}

read -p "Github Username (not email): " username

git push https://$username@$GITHUB $branch
git push https://$username@$GITHUB --tags

if [ $? -eq 0 ]; then
  bash get.sh
fi
