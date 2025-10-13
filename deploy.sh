#!/usr/bin/env sh

docker build -t breakcoresnake . && docker tag breakcoresnake seidenschnabel2k/breakcoresnake && docker push seidenschnabel2k/breakcoresnake
