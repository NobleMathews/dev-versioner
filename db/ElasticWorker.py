from elasticsearch import Elasticsearch


def connect_elasticsearch(target: dict) -> Elasticsearch:
    """Connect to local elastic server"""
    _es = None
    _es = Elasticsearch([target])
    if _es.ping():
        print('Connected to Elastic')
        create_index(_es, "python")
        create_index(_es, "javascript")
        create_index(_es, "go")
    else:
        print('Failed to connect!')
    return _es


def create_index(es: Elasticsearch, index_name: str = "versioner") -> None:
    """Populating Elastic with strict schema to index"""
    config = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 1
        }
    }
    es.indices.create(index=index_name, ignore=400, **config)
