# Distributed-Provenance
Distributed-Provenance Project

# node-python
Python implementation of the node

## Team
- Tzu-Chuan Lin
- Yu-Che Lin
- Mu-Te Shen
- Jiafan Zhang





# Development

## Prerequisites
- grpcio-tools
```shell script
pip3 install -r requirements.txt
```

## Generate python file from proto
```shell script
python3 -m grpc_tools.protoc -I protos --python_out=. --grpc_python_out=. protos/*.proto
```

**WARNING** If you regenerated the grpc files, you'll have to modify the import route in each `_grpc.py` files

## Run
This should fail with `failed to connect to all addresses` now. It's still valuable to check for syntax error tho
```shell script
python3 node.py
```
