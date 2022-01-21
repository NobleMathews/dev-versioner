"""
License Extractor

This script extracts license information from various version control systems
these may not support semantic versioning (https://semver.org/)

    Popular options NPM supports for hosting packages - Github  - Gitlab - Bitbucket
    (https://blog.npmjs.org/post/154387331670/the-right-tool-for-the-job-why-not-to-use-version.html)

    - Rate limits and authentication [handled]
    ! user/repo but still commit hash - branch - version
        There may exist copies in other repositories
            gopkg.in/yaml.v1 - https://github.com/go-yaml/yaml/tree/v1
    - how does license api work when github cannot identify type of file [handled]

"""
import Constants
from github import Github
from bs4 import BeautifulSoup
import re
import json
import requests
import requests_cache

requests_cache.install_cache('test_cache', expire_after=1800)

source = Constants.REGISTRY


def parse_license(license_file, license_dict):
    """
    Checks the license file contents to return possible license type
    :param license_file: String containing license file contents
    :param license_dict: Dictionary mapping license files and unique substring
    :return: Detected license type as a String, Other if failed to detect
    """
    for lic in license_dict:
        if lic in license_file:
            return license_dict[lic]
    return "Other"


def make_vcs_request(dependency):
    """
    Fall through to VCS check for a go namespace (only due to go.mod check)
    :param dependency: package not found in other repositories
    :return: result object with name version license and dependencies
    """
    result = {}
    if "github.com" in dependency:
        # Github
        g = Github(Constants.GITHUB_TOKEN)
        repo_identifier = re.search(r"github.com/([^/]+)/([^/.\r\n]+)", dependency)
        repo = g.get_repo(repo_identifier.group(1)+"/"+repo_identifier.group(2))
        repo_license = repo.get_license()
        if repo_license.license.name == "Other":
            repo_lic = parse_license(repo_license.decoded_content.decode(), Constants.LICENSE_DICT)
        else:
            repo_lic = repo_license.license.name
        releases = [release.tag_name for release in repo.get_releases()]
        # ! this may have unintended consequences like missing release info
        if len(releases) == 0:
            releases = [tag.name for tag in repo.get_tags()]
        print(releases)
        dep_file = repo.get_contents("go.mod").decoded_content.decode()
        # require .. .. or require ( .. .. \n .. ..)
        dep_data = re.findall(r"[\s/]+([^\s\n(]+)\s+v([^\s\n]+)", dep_file)
        data = dict(dep_data)
        result['name'] = dependency
        result['version'] = releases[0]
        result['license'] = repo_lic
        result['dependencies'] = data
    # TODO [Gitlab, Bitbucket]
    return result


def make_url(language, package, version=""):
    """
    Construct the API JSON request URL or web URL to scrape
    :param language: python, javascript or go
    :param package: as imported
    :param version: optional
    :return: str(url) to fetch
    """
    if language == "python":
        if version:
            url_elements = (source[language]['url'], package, version, 'json')
        else:
            url_elements = (source[language]['url'], package, 'json')
    elif language == "javascript":
        if version:
            url_elements = (source[language]['url'], package, version)
        else:
            url_elements = (source[language]['url'], package)
    else:  # GO
        url_elements = (source[language]['url'], package)
    return "/".join(url_elements).rstrip("/")


def make_single_request(language, package):
    """
    Obtain package license and dependency information.
    :param language: python, javascript or go
    :param package: as imported
    :return: result object with name version license and dependencies
    """
    result = {}
    url = make_url(language, package)
    print(url)
    response = requests.get(url)
    name = source[language]['name']
    version = source[language]['version']
    licence = source[language]['license']
    dependencies = source[language]['dependency']

    if language == "python":
        data = json.loads(response.text)
        result['name'] = data["info"][name]
        result['version'] = data["info"][version]
        result['license'] = data["info"][licence]
        result['dependencies'] = data["info"][dependencies]
    elif language == "javascript":
        data = json.loads(response.text)
        if 'versions' in data.keys():
            latest = data['dist-tags']['latest']
            result['name'] = data['versions'][latest][name]
            result['version'] = latest
            result['license'] = data['versions'][latest]['license']
            result['dependencies'] = data['versions'][latest]['dependencies']
        else:
            result['name'] = data[name]
            result['version'] = data[version]
            result['license'] = data[licence]
            result['dependencies'] = data[dependencies]
    else:  # GO
        # if "Oops! We couldn't find" not in response.text:
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
                print(releases)
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

    return result


def make_multiple_requests(language, packages):
    """
    Obtain license and dependency information for list of packages.
    :param language: python, javascript or go
    :param packages: a list of dependencies in each language
    :return: result object with name version license and dependencies
    """
    result = {}

    for package in packages:
        result[package] = make_single_request(language, package)
    return result


def main():
    """Main function for testing"""
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
    # print(make_single_request('javascript', 'react'))
    for lang, dependencies in dependency_list.items():
        print(json.dumps(make_multiple_requests(lang, dependencies), indent=3))


if __name__ == "__main__":
    main()
