"""
License Extractor

This script extracts license information from various version control systems
these may not support semantic versioning (https://semver.org/)

    ! Popular options NPM supports for hosting packages - GitHub  - Gitlab - Bitbucket
    ! Rate limits
    ! user/repo but still commit hash - branch - version
        There may exist copies in other repositories
            gopkg.in/yaml.v1 - https://github.com/go-yaml/yaml/tree/v1

"""
import Constants
from bs4 import BeautifulSoup
import re
import json
import requests
import requests_cache
from datetime import datetime, timedelta
from db.ElasticWorker import Elasticsearch, connect_elasticsearch
from helper import Result
from vcs.GithubWorker import handle_github
import logging
from typing import List, TypedDict, Optional

requests_cache.install_cache('test_cache', expire_after=Constants.CACHE_EXPIRY)
source: dict = Constants.REGISTRY


def make_vcs_request(
        dependency: str
) -> Result:
    """
    Fall through to VCS check for a go namespace (only due to go.mod check)
    :param dependency: package not found in other repositories
    :return: result object with name version license and dependencies
    """
    result = {}
    if "github.com" in dependency:
        result = handle_github(dependency)
    else:
        logging.error("VCS Request Failed: Unsupported Pattern")
        logging.info("VCS for BitBucket and GitLab coming soon!")
    return result


def make_url(
        language: str,
        package: str,
        version: str = ""
) -> str:
    """
    Construct the API JSON request URL or web URL to scrape
    :param language: python, javascript or go
    :param package: as imported
    :param version: optional
    :return: url to fetch
    """
    match language:
        case "python":
            if version:
                url_elements = (source[language]['url'], package, version, 'json')
            else:
                url_elements = (source[language]['url'], package, 'json')
        case "javascript":
            if version:
                url_elements = (source[language]['url'], package, version)
            else:
                url_elements = (source[language]['url'], package)
        case "go":
            url_elements = (source[language]['url'], package)
        case _:
            logging.error("This language is not supported")
            return ""
    return "/".join(url_elements).rstrip("/")


def make_single_request(
        es: Elasticsearch,
        language: str,
        package: str,
        version: str = ""
) -> Result:
    """
    Obtain package license and dependency information.
    :param es: ElasticSearch Instance
    :param language: python, javascript or go
    :param package: as imported
    :param version: check for specific version
    :return: result object with name version license and dependencies
    """
    ESresult: dict = es.get(index=language, id=package, ignore=404)
    if ESresult["found"]:
        db_time = datetime.fromisoformat(
            ESresult["_source"]["timestamp"],
        )
        if db_time - datetime.utcnow() < timedelta(
                seconds=Constants.CACHE_EXPIRY
        ):
            logging.info("Using " + package + " found in ES Database")
            return ESresult["_source"]
    result = {}
    url = make_url(language, package, version)
    logging.info(url)
    response = requests.get(url)
    name = source[language]['name']
    version = source[language]['version']
    licence = source[language]['license']
    dependencies = source[language]['dependency']
    match language:
        case "python":
            data = json.loads(response.text)
            result['name'] = package
            # data["info"][name]
            result['version'] = data["info"][version]
            result['license'] = data["info"][licence]
            result['dependencies'] = data["info"][dependencies]
        case "javascript":
            data = json.loads(response.text)
            if 'versions' in data.keys():
                latest = data['dist-tags']['latest']
                result['name'] = package
                # data['versions'][latest][name]
                result['version'] = latest
                result['license'] = data['versions'][latest]['license']
                result['dependencies'] = data['versions'][latest]['dependencies']
            else:
                result['name'] = package
                result['version'] = data[version]
                result['license'] = data[licence]
                result['dependencies'] = data[dependencies]
        case "go":
            if response.status_code != 400:
                soup = BeautifulSoup(response.text, "html.parser")
                name_parse = name.split('.')
                name_data = soup.find(
                    name_parse[0],
                    class_=name_parse[1]
                ).getText().strip().split(" ")
                if len(name_data) > 1:
                    package_name = name_data[-1].strip()
                else:
                    package_name = package
                key_parse = source[language]['parse'].split('.')
                ver_parse = source[language]['versions'].split('.')
                dep_parse = source[language]['dependencies'].split('.')
                key_element = soup.find(
                    key_parse[0],
                    class_=key_parse[1]
                ).getText()
                key_data = re.findall(r"([^ \n:]+): ([a-zA-Z0-9-_ ,.]+)", key_element)
                data = dict(key_data)
                ver_res = requests.get(url + "?tab=versions", allow_redirects=False)
                dep_res = requests.get(url + "?tab=imports", allow_redirects=False)
                if ver_res.status_code == 200:
                    version_soup = BeautifulSoup(ver_res.text, "html.parser")
                    releases = [
                        release.getText().strip()
                        for release in version_soup.findAll(
                            ver_parse[0],
                            class_=ver_parse[1]
                        )
                    ]
                    logging.info(releases)
                dependencies = []
                if dep_res.status_code == 200:
                    dep_soup = BeautifulSoup(dep_res.text, "html.parser")
                    dependencies = [
                        dependency.getText().strip()
                        for dependency in dep_soup.findAll(
                            dep_parse[0],
                            class_=dep_parse[1]
                        )
                    ]
                result['name'] = package_name
                result['version'] = data[version]
                result['license'] = data[licence]
                result['dependencies'] = dependencies
            else:
                result = make_vcs_request(package)
    result["timestamp"] = datetime.utcnow().isoformat()
    es.index(
        index=language,
        id=package,
        document=result
    )
    return result


def make_multiple_requests(
        es: Elasticsearch,
        language: str,
        packages: List[str]
) -> dict:
    """
    Obtain license and dependency information for list of packages.
    :param es: ElasticSearch Instance
    :param language: python, javascript or go
    :param packages: a list of dependencies in each language
    :return: result object with name version license and dependencies
    """
    result = {}

    for package in packages:
        result[package] = make_single_request(es, language, package)
    return result


def main():
    """Main function for testing"""
    es = connect_elasticsearch({'host': 'localhost', 'port': 9200})
    dependency_list = {
        'javascript':
            [
                'react',
            ],
        "python":
            [
                'pygithub'
            ],
        "go":
            [
                "https://github.com/deepsourcelabs/cli",
                "https://github.com/go-yaml/yaml",
                "github.com/getsentry/sentry-go",
                "github.com/cactus/go-statsd-client/v5/statsd",
                "github.com/guseggert/pkggodev-client",
            ]
    }
    for lang, dependencies in dependency_list.items():
        logging.info(
            json.dumps(
                make_multiple_requests(es, lang, dependencies),
                indent=3
            )
        )


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    main()
