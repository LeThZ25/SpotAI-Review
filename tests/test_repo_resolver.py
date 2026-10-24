import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from spotai.repo_resolver import RepoResolver, RepoResolverError


class TestRepoResolver(unittest.TestCase):
    def setUp(self):
        self.resolver = RepoResolver(temp_base_dir="temp_repos_test")

    def test_is_git_url(self):
        self.assertTrue(RepoResolver.is_git_url("https://github.com/psf/requests.git"))
        self.assertTrue(RepoResolver.is_git_url("http://gitlab.com/user/project"))
        self.assertTrue(RepoResolver.is_git_url("git@github.com:octocat/Hello-World.git"))
        self.assertTrue(RepoResolver.is_git_url("https://bitbucket.org/owner/repo"))
        
        self.assertFalse(RepoResolver.is_git_url("sample_repos/repo1_ecommerce_java"))
        self.assertFalse(RepoResolver.is_git_url("C:\\path\\to\\my_repo"))
        self.assertFalse(RepoResolver.is_git_url("/home/user/project"))
        self.assertFalse(RepoResolver.is_git_url(""))

    def test_extract_repo_name(self):
        self.assertEqual(
            RepoResolver.extract_repo_name("https://github.com/psf/requests.git"),
            "requests"
        )
        self.assertEqual(
            RepoResolver.extract_repo_name("https://github.com/pallets/flask"),
            "flask"
        )
        self.assertEqual(
            RepoResolver.extract_repo_name("git@github.com:octocat/Hello-World.git"),
            "Hello-World"
        )
        self.assertEqual(
            RepoResolver.extract_repo_name("sample_repos/repo1_ecommerce_java"),
            "repo1_ecommerce_java"
        )

    def test_resolve_local_existing_path(self):
        sample_path = os.path.join(os.path.dirname(__file__), "..", "sample_repos", "repo1_ecommerce_java")
        resolved_path, is_temp, name = self.resolver.resolve(sample_path)
        self.assertFalse(is_temp)
        self.assertEqual(name, "repo1_ecommerce_java")
        self.assertTrue(os.path.isdir(resolved_path))

    def test_resolve_nonexistent_local_path_raises_friendly_error(self):
        with self.assertRaises(RepoResolverError) as ctx:
            self.resolver.resolve("path/that/does/not/exist_12345")
        self.assertIn("không tồn tại", str(ctx.exception))

    def test_resolve_empty_string_raises_friendly_error(self):
        with self.assertRaises(RepoResolverError) as ctx:
            self.resolver.resolve("   ")
        self.assertIn("không được để trống", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
