#!/usr/bin/env bash

# check whether git repo is dirty or clean
if $(git diff --quiet)
then
    echo clean
else 
    echo dirty
fi
