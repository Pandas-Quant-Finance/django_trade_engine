import cProfile
from pstats import Stats


class CProfileUnitTest(object):
    """a simple test"""

    def setUp(self):
        """init each test"""
        self.pr = cProfile.Profile()
        self.pr.enable()

    def tearDown(self):
        """finish any test"""
        p = Stats(self.pr)
        p.strip_dirs()
        p.sort_stats('cumtime')
        p.print_stats()
