"""腾讯云客户端工厂"""

from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.lighthouse.v20200324 import lighthouse_client
from tencentcloud.tat.v20201028 import tat_client


def create_credential(config):
    """创建腾讯云认证凭据"""
    return credential.Credential(config["secret_id"], config["secret_key"])


def create_lighthouse_client(cred, config):
    """创建 Lighthouse 客户端"""
    http_profile = HttpProfile()
    http_profile.endpoint = "lighthouse.tencentcloudapi.com"
    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile
    return lighthouse_client.LighthouseClient(cred, config["region"], client_profile)


def create_tat_client(cred, config):
    """创建 TAT 客户端"""
    http_profile = HttpProfile()
    http_profile.endpoint = "tat.tencentcloudapi.com"
    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile
    return tat_client.TatClient(cred, config["region"], client_profile)
