"""Replaceable demo identity and delivery verification."""


class DemoIdentity:
    simulated = True

    def resolve(self, selector):
        return selector.lower()


class DemoDeliveryVerifier:
    simulated = True

    def verify(self, pr_url):
        return {'verified': True, 'simulated': True, 'pr_url': pr_url}
