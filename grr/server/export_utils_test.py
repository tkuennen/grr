#!/usr/bin/env python
"""Tests for export utils functions."""

import os
import stat


from grr.lib import flags
from grr.lib import rdfvalue
from grr.lib import utils
from grr.lib.rdfvalues import client as rdf_client
from grr.lib.rdfvalues import file_finder as rdf_file_finder
from grr.lib.rdfvalues import paths as rdf_paths
from grr.server import aff4
from grr.server import data_store
from grr.server import export_utils
from grr.server import sequential_collection
from grr.server.aff4_objects import aff4_grr
from grr.server.aff4_objects import standard
from grr.server.flows.general import collectors
from grr.server.hunts import results
from grr.test_lib import flow_test_lib
from grr.test_lib import test_lib


class TestExports(flow_test_lib.FlowTestsBaseclass):
  """Tests exporting of data."""

  def setUp(self):
    super(TestExports, self).setUp()

    self.out = self.client_id.Add("fs/os")
    self.CreateFile("testfile1")
    self.CreateFile("testfile2")
    self.CreateFile("testfile5")
    self.CreateFile("testfile6")
    self.CreateDir("testdir1")
    self.CreateFile("testdir1/testfile3")
    self.CreateDir("testdir1/testdir2")
    self.CreateFile("testdir1/testdir2/testfile4")

    self.collection_urn = self.client_id.Add("testcoll")

  def CreateDir(self, dirpath):
    path = self.out.Add(*dirpath.split("/"))
    fd = aff4.FACTORY.Create(path, standard.VFSDirectory, token=self.token)
    fd.Close()

  def CreateFile(self, filepath):
    path = self.out.Add(filepath)
    fd = aff4.FACTORY.Create(path, aff4_grr.VFSMemoryFile, token=self.token)
    fd.Write("some data")
    fd.Close()

  def testExportFile(self):
    """Check we can export a file without errors."""
    with utils.TempDirectory() as tmpdir:
      export_utils.CopyAFF4ToLocal(
          self.out.Add("testfile1"), tmpdir, overwrite=True, token=self.token)
      expected_outdir = os.path.join(tmpdir, self.out.Path()[1:])
      self.assertTrue("testfile1" in os.listdir(expected_outdir))

  def _VerifyDownload(self):
    with utils.TempDirectory() as tmpdir:
      export_utils.DownloadCollection(
          self.collection_urn,
          tmpdir,
          overwrite=True,
          dump_client_info=True,
          token=self.token,
          max_threads=2)
      expected_outdir = os.path.join(tmpdir, self.out.Path()[1:])

      # Check we found both files.
      self.assertTrue("testfile1" in os.listdir(expected_outdir))
      self.assertTrue("testfile2" in os.listdir(expected_outdir))
      self.assertTrue("testfile5" in os.listdir(expected_outdir))
      self.assertTrue("testfile6" in os.listdir(expected_outdir))

      # Check we dumped a YAML file to the root of the client.
      expected_rootdir = os.path.join(tmpdir, self.client_id.Basename())
      self.assertTrue("client_info.yaml" in os.listdir(expected_rootdir))

  def testDownloadHuntResultCollection(self):
    """Check we can download files references in HuntResultCollection."""
    # Create a collection with URNs to some files.
    fd = results.HuntResultCollection(self.collection_urn)
    with data_store.DB.GetMutationPool() as pool:
      fd.AddAsMessage(
          rdfvalue.RDFURN(self.out.Add("testfile1")),
          self.client_id,
          mutation_pool=pool)
      fd.AddAsMessage(
          rdf_client.StatEntry(
              pathspec=rdf_paths.PathSpec(path="testfile2", pathtype="OS")),
          self.client_id,
          mutation_pool=pool)
      fd.AddAsMessage(
          rdf_file_finder.FileFinderResult(stat_entry=rdf_client.StatEntry(
              pathspec=rdf_paths.PathSpec(path="testfile5", pathtype="OS"))),
          self.client_id,
          mutation_pool=pool)
      fd.AddAsMessage(
          collectors.ArtifactFilesDownloaderResult(
              downloaded_file=rdf_client.StatEntry(pathspec=rdf_paths.PathSpec(
                  path="testfile6", pathtype="OS"))),
          self.client_id,
          mutation_pool=pool)
    self._VerifyDownload()

  def testDownloadGeneralIndexedCollection(self):
    """Check we can download files references in GeneralIndexedCollection."""
    fd = sequential_collection.GeneralIndexedCollection(self.collection_urn)
    self._AddTestData(fd)
    self._VerifyDownload()

  def _AddTestData(self, fd):
    with data_store.DB.GetMutationPool() as pool:
      fd.Add(rdfvalue.RDFURN(self.out.Add("testfile1")), mutation_pool=pool)
      fd.Add(
          rdf_client.StatEntry(
              pathspec=rdf_paths.PathSpec(path="testfile2", pathtype="OS")),
          mutation_pool=pool)
      fd.Add(
          rdf_file_finder.FileFinderResult(stat_entry=rdf_client.StatEntry(
              pathspec=rdf_paths.PathSpec(path="testfile5", pathtype="OS"))),
          mutation_pool=pool)
      fd.Add(
          collectors.ArtifactFilesDownloaderResult(
              downloaded_file=rdf_client.StatEntry(pathspec=rdf_paths.PathSpec(
                  path="testfile6", pathtype="OS"))),
          mutation_pool=pool)

  def testDownloadCollectionIgnoresArtifactResultsWithoutFiles(self):
    # Create a collection with URNs to some files.
    fd = sequential_collection.GeneralIndexedCollection(self.collection_urn)
    with data_store.DB.GetMutationPool() as pool:
      fd.Add(collectors.ArtifactFilesDownloaderResult(), mutation_pool=pool)

    with utils.TempDirectory() as tmpdir:
      export_utils.DownloadCollection(
          self.collection_urn,
          tmpdir,
          overwrite=True,
          dump_client_info=True,
          token=self.token,
          max_threads=2)
      expected_outdir = os.path.join(tmpdir, self.out.Path()[1:])
      self.assertFalse(os.path.exists(expected_outdir))

  def testDownloadCollectionWithFlattenOption(self):
    """Check we can download files references in a collection."""
    # Create a collection with URNs to some files.
    fd = sequential_collection.GeneralIndexedCollection(self.collection_urn)
    with data_store.DB.GetMutationPool() as pool:
      fd.Add(rdfvalue.RDFURN(self.out.Add("testfile1")), mutation_pool=pool)
      fd.Add(
          rdf_client.StatEntry(
              pathspec=rdf_paths.PathSpec(path="testfile2", pathtype="OS")),
          mutation_pool=pool)
      fd.Add(
          rdf_file_finder.FileFinderResult(stat_entry=rdf_client.StatEntry(
              pathspec=rdf_paths.PathSpec(path="testfile5", pathtype="OS"))),
          mutation_pool=pool)

    with utils.TempDirectory() as tmpdir:
      export_utils.DownloadCollection(
          self.collection_urn,
          tmpdir,
          overwrite=True,
          dump_client_info=True,
          flatten=True,
          token=self.token,
          max_threads=2)

      # Check that "files" folder is filled with symlinks to downloaded files.
      symlinks = os.listdir(os.path.join(tmpdir, "files"))
      self.assertEqual(len(symlinks), 3)
      self.assertListEqual(
          sorted(symlinks), [
              "C.1000000000000000_fs_os_testfile1",
              "C.1000000000000000_fs_os_testfile2",
              "C.1000000000000000_fs_os_testfile5"
          ])
      self.assertEqual(
          os.readlink(
              os.path.join(tmpdir, "files",
                           "C.1000000000000000_fs_os_testfile1")),
          os.path.join(tmpdir, "C.1000000000000000", "fs", "os", "testfile1"))

  def testDownloadCollectionWithFoldersEntries(self):
    """Check we can download a collection that also references folders."""
    fd = sequential_collection.GeneralIndexedCollection(self.collection_urn)
    with data_store.DB.GetMutationPool() as pool:
      fd.Add(
          rdf_file_finder.FileFinderResult(stat_entry=rdf_client.StatEntry(
              pathspec=rdf_paths.PathSpec(path="testfile5", pathtype="OS"))),
          mutation_pool=pool)
      fd.Add(
          rdf_file_finder.FileFinderResult(stat_entry=rdf_client.StatEntry(
              pathspec=rdf_paths.PathSpec(path="testdir1", pathtype="OS"),
              st_mode=stat.S_IFDIR)),
          mutation_pool=pool)

    with utils.TempDirectory() as tmpdir:
      export_utils.DownloadCollection(
          self.collection_urn,
          tmpdir,
          overwrite=True,
          dump_client_info=True,
          token=self.token,
          max_threads=2)
      expected_outdir = os.path.join(tmpdir, self.out.Path()[1:])

      # Check we found both files.
      self.assertTrue("testfile5" in os.listdir(expected_outdir))
      self.assertTrue("testdir1" in os.listdir(expected_outdir))

  def testRecursiveDownload(self):
    """Check we can export a file without errors."""
    with utils.TempDirectory() as tmpdir:
      export_utils.RecursiveDownload(
          aff4.FACTORY.Open(self.out, token=self.token), tmpdir, overwrite=True)
      expected_outdir = os.path.join(tmpdir, self.out.Path()[1:])
      self.assertTrue("testfile1" in os.listdir(expected_outdir))
      full_outdir = os.path.join(expected_outdir, "testdir1", "testdir2")
      self.assertTrue("testfile4" in os.listdir(full_outdir))


def main(argv):
  test_lib.main(argv)


if __name__ == "__main__":
  flags.StartMain(main)
