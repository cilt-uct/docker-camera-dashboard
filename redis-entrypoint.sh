#!/bin/sh
cp /redis-base.conf /redis.conf
echo "requirepass $(cat /run/secrets/redis_password)" >> /redis.conf
exec redis-server /redis.conf
