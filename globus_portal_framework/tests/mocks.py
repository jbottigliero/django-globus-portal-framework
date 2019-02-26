from datetime import datetime
import pytz
from django.contrib.auth.models import User
from django.test import Client
from django.urls import path, include
from social_django.models import UserSocialAuth
import globus_sdk

# Two days in seconds
TOKEN_EXPIRE_TIME = 48 * 60 * 60


class MockGlobusClient:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class MockTransferAPIError(Exception):
    """Mock Globus exception"""
    def __init__(self, code='', message=''):
        self.code = code
        self.message = message


class MockTransferClient(MockGlobusClient):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.raise_on_ls = kwargs.get('raise_on_ls', False)
        self.exc_code = kwargs.get('exc_code', 'ExternalError.'
                                               'DirListingFailed.NotDirectory')
        self.exc_mess = kwargs.get('message', '')

    def operation_ls(self, *args, **kwargs):
        if self.raise_on_ls:
            exc = globus_sdk.TransferAPIError()
            exc.code = self.exc_code
            exc.message = self.exc_mess
            raise exc


def mock_user(username, tokens):
    """
    Give a username and tokens and this will mock out python_social_auth
    with the given globus tokens.
    :param username: Any string, such as 'bob' or 'joe@globusid.org'
    :param tokens: token scopes, such as ['search.api.globus.org']
    :return: Django User Object
    """
    user = User.objects.create_user(username, username + '@globus.org',
                                    'globusrocks')
    extra_data = {
        'user': user,
        'provider': 'globus',
        'extra_data': {
            'other_tokens': [{
                'resource_server': token,
                'access_token': 'foo', 'expires_in': TOKEN_EXPIRE_TIME
            } for token in tokens],
            'access_token': 'auth_access_token',
            'refresh_token': 'auth_refresh_token'
        }
    }
    user.last_login = datetime.now(pytz.utc)
    soc_auth = UserSocialAuth.objects.create(**extra_data)
    user.provider = 'globus'
    user.save()
    soc_auth.save()
    return user


def get_logged_in_client(username, tokens):
    c = Client()
    user = mock_user(username, tokens)
    # Password is set in mocks, and is always 'globusrocks' for this func
    c.login(username=username, password='globusrocks')
    return c, user


def globus_client_is_loaded_with_authorizer(client):
    return isinstance(client.kwargs.get('authorizer'),
                      globus_sdk.AccessTokenAuthorizer)


def rebuild_index_urlpatterns(old_urlpatterns):
    """
    This fixes pre-complied paths not matching new test paths. Since paths
    are compiled at import time, if you override settings with new
    SEARCH_INDEXES, your new search indexes won't have urls that match due to
    the regexes already being compiled. The problem stems from IndexConverter
    containing explicit names of the SEARCH_INDEXES which don't handle change
    well. Use this function to rebuild the names to pick up on your test index
    names.
    :param old_urlpatterns: patterns you want to rebuild
    :return: urlpatterns
    """
    urlpatterns = [
        path('', include('social_django.urls', namespace='social')),
        # FIXME Remove after merging #55 python-social-auth-upgrade
        path('', include('django.contrib.auth.urls'))
    ]

    for url in old_urlpatterns:
        if '<index:index>' in str(url.pattern):
            urlpatterns.append(path(str(url.pattern), url.callback,
                                    name=url.name))
        else:
            urlpatterns.append(url)

    return urlpatterns
