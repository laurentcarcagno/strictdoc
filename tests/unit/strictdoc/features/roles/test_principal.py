from strictdoc.features.roles.principal import (
    Principal,
    groups_from_header,
    principal_from_headers,
)


def test_001_groups_drop_the_realm_roles_and_blanks():
    header = (
        "infra-admins,role:offline_access, strictdoc-authors ,,"
        "role:default-roles-infra"
    )
    assert groups_from_header(header) == ("infra-admins", "strictdoc-authors")
    assert groups_from_header("") == ()
    assert groups_from_header("réviseurs,équipe 1") == (
        "réviseurs",
        "équipe 1",
    )


def test_002_the_user_name_comes_from_the_preferred_username():
    principal = principal_from_headers(
        {
            "x-forwarded-user": "002b056a-a9ca-4369-828f-13abe69ae6c9",
            "x-forwarded-preferred-username": "laurent.carcagno",
            "x-forwarded-email": "laurent.carcagno@hemeria-group.com",
            "x-forwarded-groups": "strictdoc-authors,role:offline_access",
        }
    )
    assert principal == Principal(
        user="laurent.carcagno",
        subject="002b056a-a9ca-4369-828f-13abe69ae6c9",
        email="laurent.carcagno@hemeria-group.com",
        groups=("strictdoc-authors",),
    )
    assert principal.authenticated


def test_003_the_name_falls_back_to_the_email_then_to_the_subject():
    assert (
        principal_from_headers(
            {"x-forwarded-user": "abc", "x-forwarded-email": "a@b.c"}
        ).user
        == "a@b.c"
    )
    assert principal_from_headers({"x-forwarded-user": "abc"}).user == "abc"


def test_004_no_identity_headers_means_no_principal():
    assert principal_from_headers({}) is None
    assert principal_from_headers({"x-forwarded-groups": "g"}) is None
    assert principal_from_headers({"x-forwarded-user": "  "}) is None


def test_005_the_auth_request_headers_are_never_read():
    assert (
        principal_from_headers(
            {
                "x-auth-request-user": "attacker",
                "x-auth-request-email": "attacker@evil",
                "x-auth-request-groups": "admins",
            }
        )
        is None
    )
    principal = principal_from_headers(
        {
            "x-forwarded-preferred-username": "real",
            "x-auth-request-user": "attacker",
        }
    )
    assert principal.user == "real"


def test_006_the_anonymous_principal_is_not_authenticated():
    principal = Principal.anonymous()
    assert principal.user == "anonymous"
    assert not principal.authenticated
    assert principal.groups == ()
