import grpc
import generated.client_comm_pb2_grpc as client_grpc
import generated.gateway_comm_pb2_grpc as gateway_grpc
import generated.master_comm_pb2_grpc as master_grpc
import generated.node_comm_pb2_grpc as node_grpc
import generated.sentinel_comm_pb2_grpc as sentinel_grpc
import generated.client_comm_pb2 as client_pb2
import generated.gateway_comm_pb2 as gateway_pb2
import generated.master_comm_pb2 as master_pb2
import generated.node_comm_pb2 as node_pb2
import generated.sentinel_comm_pb2 as sentinel_pb2

node_ip = '127.0.0.1:50051'

def test_health_check():
    with grpc.insecure_channel(node_ip, options=(('grpc.enable_http_proxy', 0),)) as node_channel:
        stub = sentinel_grpc.SentinelMonitoringStub(node_channel)
        response = stub.healthCheck(sentinel_pb2.healthCheckRequest())
        print(response)


def file_to_request(filename):
    with open(filename, 'rb') as f:
        chunk = f.read(1000)
        while len(chunk) > 0:
            request = client_pb2.UploadFileRequest(filename=filename, payload=chunk)
            chunk = f.read(1000)
            yield request

FILENAME = 'test.txt'

def test_upload_file():
    with grpc.insecure_channel(node_ip, options=(('grpc.enable_http_proxy', 0),)) as node_channel:
        stub = client_grpc.StreamingStub(node_channel)

        response = stub.UploadFile(file_to_request(FILENAME))
        print(response)


def test_download_file():
    with grpc.insecure_channel(node_ip, options=(('grpc.enable_http_proxy', 0),)) as node_channel:
        stub = client_grpc.StreamingStub(node_channel)

        response = stub.DownloadFile(client_pb2.DownloadFileRequest(filename=FILENAME))

        with open('downloaded_' + FILENAME, 'wb') as f:
            for chunk in response:
                print(chunk.error)
                f.write(chunk.payload)

def testReplicateFile():
    with grpc.insecure_channel(node_ip, options=(('grpc.enable_http_proxy', 0),)) as node_channel:
        stub = node_grpc.NodeReplicationStub(node_channel)
        response = stub.ReplicateFile(node_pb2.ReplicateFileRequest(
            filename=FILENAME,
            nodeips=['localhost:50052']
        ))


def main():
    test_health_check()
    test_upload_file()
    test_download_file()
    testReplicateFile()

if __name__ == '__main__':
    main()