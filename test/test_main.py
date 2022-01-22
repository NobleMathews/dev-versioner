import main
from db.ElasticWorker import connect_elasticsearch

es = connect_elasticsearch({'host': 'localhost', 'port': 9200})


def test_elasticsearch():
    assert es is not None


def test_make_url_with_version():
    assert main.make_url('python', 'aiohttp', '3.7.2') == 'https://pypi.org/pypi/aiohttp/3.7.2/json'


def test_make_url_without_version():
    assert main.make_url('python', 'aiohttp') == 'https://pypi.org/pypi/aiohttp/json'


def test_make_single_request_py():
    result = main.make_single_request(es, "python", "aiohttp", "3.7.2")
    assert result['name'] == 'aiohttp'
    assert result['version'] == '3.7.2'
    assert result['license'] == 'Apache 2'
    assert len(result['dependencies']) == 10


def test_make_single_request_js():
    result = main.make_single_request(es, "javascript", "react", "17.0.2")
    assert result['name'] == 'react'
    assert result['version'] == '17.0.2'
    assert result['license'] == 'MIT'
    assert len(result['dependencies']) == 2

