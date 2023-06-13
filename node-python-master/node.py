import grpc
from absl import app, logging
import json
import os
from operator import itemgetter
from concurrent import futures

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

GATEWAY_IP = 'localhost:1234'
NODE_IP = 'ugh:what'
NODE_NAME = 'Pikapika'
NODE_PASSWORD = 'pikachu!@#_TO_the_MOON!!!'


class NodeCluster(node_grpc.NodeReplicationServicer, client_grpc.StreamingServicer, sentinel_grpc.SentinelMonitoringServicer):
    jwt_token = None
    master_ip = None
    file_root_dir = './data/'

    def __init__(self, port, gateway_ip):
        logging.info('Starting NodeCluster ... ')
        self.gateway_ip = gateway_ip
        self.port = port
        self.login_or_register()

    def login_or_register(self):
        logging.info('Authenticating with Gateway ...')
        with grpc.insecure_channel(self.gateway_ip) as gateway_channel:
            stub = gateway_grpc.AuthenticateStub(gateway_channel)
            auth_response = stub.Login(gateway_pb2.Request(
                ip=NODE_IP,
                password=NODE_PASSWORD,
                type="NODE"
            ))

            if auth_response.message != 'SUCCESS':
                auth_response = stub.Register(gateway_pb2.Request(
                    ip=NODE_IP,
                    password=NODE_PASSWORD,
                    type="NODE"
                ))

            message, token, master_ip = itemgetter('message', 'token', 'masterip')(auth_response)

            if message != 'SUCCESS':
                raise ConnectionRefusedError('Failed to register with the Gateway')
            if not master_ip or not token:
                raise Exception('Did not receive master_ip or jwt token from gateway')

            self.jwt_token = token
            self.master_ip = master_ip

    def CreateReplica(self, request_iterator, context):

        for n in request_iterator:
            filename = n.filename
            first_payload = n.payload
            break

        logging.info('CreateReplica: ', filename)

        filepath = self.get_file_path(filename)
        try:
            with open(filepath, 'wb') as f:
                f.write(first_payload)
                for request in request_iterator:
                    f.write(request.payload)

            return node_pb2.CreateReplicaReply(status='SUCCESS')

        except:
            return node_pb2.CreateReplicaReply(status='FAILURE')

    def get_node_ips_for_replication(self, filename):
        """
        This function should only be called AFTER an upload has completed
        """
        try:
            with grpc.insecure_channel(self.master_ip) as master_channel:
                stub = master_grpc.ReplicationStub(master_channel)
                node_ips_response = stub.GetNodeIpsForReplication(
                    master_pb2.NodeIpsRequest(filename=filename)
                )

            return node_ips_response.nodeips
        except:
            logging.error("Failed to acquire node ips from master")
            return []

    def file_to_create_replica_request(self,filename):
        with open(self.get_file_path(filename), 'rb') as f:
            chunk = f.read(1000)
            while len(chunk) > 0:
                response = node_pb2.CreateReplicaRequest(filename=filename, payload=chunk)
                chunk = f.read(1000)
                yield response

    def replicate_file(self, filename, node_ips):
        error = None
        for node_ip in node_ips:
            if not self.find_files(filename, self.file_root_dir):
                return "FAILURE"

            with grpc.insecure_channel(node_ip) as other_node_channel:
                try:
                    stub = node_grpc.NodeReplicationStub(other_node_channel)
                    replica_response = stub.CreateReplica(self.file_to_create_replica_request(filename))
                    if replica_response.status != 'SUCCESS':
                        raise Exception("Replication failed")
                    logging.info('Successfully replicate file [%s] to node [%s]' %(filename, node_ip))
                except Exception as e:
                    logging.error('Failed to replicate file [%s] to node [%s]' %(filename, node_ip))
                    error = str(e)

        return error

    # receive ReplicateFile request
    def ReplicateFile(self, request, context):
        # parse request
        try:
            filename = request.filename
            node_ips = request.nodeips
        except:
            print ("The request is invalid.")
            return node_pb2.ReplicateFileResponse(status = "FAILURE")

        logging.info('ReplicateFile: ', filename, node_ips)
        # do replication
        error = self.replicate_file(filename, node_ips)

        if error is None:
            return node_pb2.ReplicateFileResponse(status = "SUCCESS")
        
        print (error)
        return node_pb2.ReplicateFileResponse(status = "FAILURE")

    # Verify client ip & token to still be valid when an upload/download request happens
    def validate_token(self, client_ip, client_token):
        with grpc.insecure_channel(self.gateway_ip) as gateway_channel:
            stub = gateway_grpc.AuthenticateStub(gateway_channel)
            validate_response = stub.ValidateToken(gateway_pb2.ValidateTokenRequest(
                client_ip=client_ip,
                token=client_token
            ))
            return validate_response.message == 'VALID'

    # TODO: Figure this out
    def get_client_ip(self, context):
        print("Context: ", context.invocation_metadata())
        for key, value in context.invocation_metadata():
            if key == 'X-Real-IP':
                return value
        return ''

    # Client-Node grpc API - UploadFile 
    def UploadFile(self, request_iterator, context):
        for n in request_iterator:
            filename = n.filename
            first_payload = n.payload
            break

        logging.info('UploadFile: ', filename)

        filepath = self.get_file_path(filename)
        client_ip = self.get_client_ip(context)
        if client_ip == '':
            return client_pb2.UploadFileReply(status='FAILURE')
        validate_response = self.validate_token(client_ip, request_iterator.token)
        if validate_response.message == 'VALID' or filename is not None:
            try:
                with open(filepath, 'wb') as f:
                    f.write(first_payload)
                    for request in request_iterator:
                        f.write(request.payload)
                # Call replicate Function to create replica on other nodes
                error = self.replicate_file(request_iterator.filename, self.get_node_ips_for_replication(request_iterator.filename))
                if error == None:
                    return client_pb2.UploadFileReply(status='SUCCESS')
                else:
                    return client_pb2.UploadFileReply(status='FAILURE')
            except:
                return client_pb2.UploadFileReply(status='FAILURE')
        else:
            return client_pb2.UploadFileReply(status='FAILURE')

    def find_files(self, filename, search_path):
        for root, dir, files in os.walk(search_path):
            if (self.port + filename) in files:
                return True
        return False

    def file_to_download_response(self,filename):
        with open(filename, 'rb') as f:
            chunk = f.read(1000)
            while len(chunk) > 0:
                response = client_pb2.DownloadFileReply(error=None, payload=chunk)
                chunk = f.read(1000)
                yield response

    # Client-Node grpc API - DownloadFile 
    def DownloadFile(self, request, context):
        logging.info('DownloadFile: ', request.filename)
        client_ip = self.get_client_ip(context)
        print("Client ip: ", client_ip)
        if client_ip == '':
            return client_pb2.DownloadFileReply(payload=None, error='No Client IP')
        validate_response = self.validate_token(client_ip, request.token)
        if validate_response.message == 'VALID':
            if not self.find_files(request.filename, self.file_root_dir):
                return iter([client_pb2.DownloadFileReply(payload=None, error='File Not Exist!')])
            filename = self.get_file_path(request.filename)
            try:
                return self.file_to_download_response(filename)
            except:
                return iter([client_pb2.DownloadFileReply(payload=None, error="IO Exception!")])
        else:
            return iter([client_pb2.DownloadFileReply(payload=None, error="Validation Failed!")])

    def healthCheck(self, request, context):
        logging.info('healthCheck ... ')
        try:
            return sentinel_pb2.healthCheckReply(status = "SUCCESS")
        except:
            return sentinel_pb2.healthCheckReply(status = "FAILURE")

    def get_file_path(self, filename):
        return self.file_root_dir + self.port + filename

def main(argv):
    port = '50051'
    gateway_ip = GATEWAY_IP
    if len(argv) == 2:
        port = argv[1]
    elif len(argv) == 3:
        port = argv[1]
        gateway_ip = argv[2]

    logging.info("Starting gRPC server on port %s ..." % (port, gateway_ip))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    node_cluster = NodeCluster(port, gateway_ip)
    node_grpc.add_NodeReplicationServicer_to_server(node_cluster, server)
    client_grpc.add_StreamingServicer_to_server(node_cluster, server)
    sentinel_grpc.add_SentinelMonitoringServicer_to_server(node_cluster, server)

    server.add_insecure_port('127.0.0.1:' + port)
    server.start()
    server.wait_for_termination()


if __name__ == '__main__':
    app.run(main)