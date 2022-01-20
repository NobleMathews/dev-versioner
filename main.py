"""
License Extractor

This script extracts license information from various version control systems
these may not support semantic versioning (https://semver.org/)

    Popular options NPM supports for hosting packages - Github  - Gitlab - Bitbucket
    (https://blog.npmjs.org/post/154387331670/the-right-tool-for-the-job-why-not-to-use-version.html)

    - Rate limits and authentication [handled]
    ! user/repo but still commit hash - branch - version
        gopkg.in/yaml.v1 - https://github.com/go-yaml/yaml/tree/v1
    - how does license api work when github cannot identify type of file [handled]

"""
import Constants
from github import Github
from bs4 import BeautifulSoup
import re
import json
import requests

source = Constants.REGISTRY


def parse_license(license_file, license_dict):
    """
    Checks the license file contents against a dictionary to return possible license type
    :param license_file: String containing license file contents
    :param license_dict: Dictionary containing a mapping between license files and unique substring
    :return: Detected license type as a String, Other if failed to detect
    """
    for lic in license_dict:
        if lic in license_file:
            return license_dict[lic]
    return "Other"


def make_vcs_request(dependency):
    result = {}
    # Github
    g = Github(Constants.GITHUB_TOKEN)
    # If all failed and fell through to VCS check for go namespace
    repo_identifier = re.search("github.com/([^/]+)/([^/.\r\n]+)", dependency)
    repo = g.get_repo(f'{repo_identifier.group(1)}/{repo_identifier.group(2)}')
    repo_license = repo.get_license()
    repo_releases = repo.get_releases()
    if repo_license.license.name == "Other":
        print(parse_license(str(repo_license.decoded_content), Constants.LICENSE_DICT))
    else:
        print(repo_license.license.name)
    for release in repo_releases:
        print(release.tag_name)

    # TODO [Gitlab, Bitbucket]
    # result['name'] = data[name]
    # result['version'] = data[version]
    # result['license'] = data[licence]
    # result['dependencies'] = data[dependencies]
    return result


def make_url(language, package, version=""):
    """
    Construct the API JSON request URL.
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
    return str("/".join(url_elements).rstrip("/"))


def make_single_request(language, package):
    """
    Obtain package license and dependency information.
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
            soup_r = soup.find('div', class_="go-Main-headerDetails").getText()
            data_s = re.findall("([^ \n:]+): ([a-zA-Z0-9-_ ,.]+)", soup_r)
            # print({span.get_text().strip() for span in soup.find('div', class_="go-Main-headerDetails").findChildren("span", recursive=False)})
            data = dict(data_s)
            result['name'] = package
            result['version'] = data[version]
            result['license'] = data[licence]
            # result['dependencies'] = data[dependencies]
        else:
            result = make_vcs_request(package)

    return result


def make_multiple_requests(language, packages):
    """
    Obtain license and dependency information for list of packages.
    """
    result = {}

    for package in packages:
        result[package] = make_single_request(language, package)
    return result


def main():
    """
    The main function
    """
    dependency_list = {
        "go":
            [
                "github.com/deepsourcelabs/cli",
                "https://github.com/go-yaml/yaml"
            ]
    }
    # print(make_single_request('javascript', 'react'))
    for lang in dependency_list:
        make_multiple_requests(lang, dependency_list[lang])


if __name__ == "__main__":
    main()
