
import itertools
import os
import re
from collections import defaultdict

from licorice import logger, config
from licorice.helper import tokenize
from licorice.models import ForwardFileGenerator as FFG
from licorice.models import BackwardFileGenerator as BFG

class LicenseParser:

    def __init__(self, keywords, licenses, vague=False):
        '''License parsing class'''
        self.file_locations = keywords # dict { keyword: [ license cachedfiles that contain it ] }
        self.licenses = licenses
        self.licenses_with_vague_words = [l for l in licenses if l.vague_words]
        self.vague = vague
        self._locations = dict()

    def get_licenses(self, path):
        '''Parse given file for present license definitions. Returns a list
            of found licenses '''
        if not os.path.exists(path):
            raise IOError("File does not exist.")
        if not os.path.isfile(path):
            raise Exception("{} is not a file.".format(path))

        matches = list() # { (line number, word index): License }
        keywords = self.file_locations.keys()
        for word, line_number, word_index in FFG(path, 0, 0).get_words_with_coordinates():
            if config.LINE_LIMIT and line_number > config.LINE_LIMIT: break # limiting the portion of the file to be read

            if self.vague:
                for l in self.licenses_with_vague_words:
                    if l not in matches and word in l.vague_words:
                        matches.append(l)

            if word in keywords:
                for f in self.file_locations[word]:
                    if f.parent in matches:
                        continue
                    if self._matches(path, f, line_number, word_index, word):
                        logger.debug('Found {}'.format(f.parent.name))
                        matches.append(f.parent)

        return list(sorted(matches, key=lambda l: l.name))


    def _matches(self, file_path, license_file, line_number, word_index, keyword):
        '''Tell if the file on file_path matches the cachedfile'''
        iterators = self._get_license_iterators(license_file, keyword)
        for (word_pair) in itertools.zip_longest( \
                FFG(file_path, line_number, word_index).get_words(), \
                BFG(file_path, line_number, word_index+1).get_words()):
            if not iterators: return False
            for it_pair in iterators:
                delete_pair = False
                for direction in 0,1:
                    iterator = it_pair[direction]
                    word = word_pair[direction]
                    if word == '\n':
                        if iterator.halted:
                            if iterator.newline_seen: delete_pair = True
                            else: iterator.newline_seen = True
                    else:
                        try:
                            iword = iterator.next()
#                            if '' in license_file.path:
#                                logger.debug('Matching {} : {}/{} (dir: {}) {}'.format(word, iword, iterator.peek(), direction, iterator))
                            if iword == '%wild%':
                                if word == iterator.peek():
                                    iterator.next()
                                    continue
                                iterator.halt()
                                iterator.newline_seen = False
                            elif word == iword:
                                if iterator.halted:
                                    iterator.resume()
                                    iterator.newline_seen = False
                            elif word == None and iterator.halted:
                                iterator.finished = True
                            else:
                                if not iterator.halted:
                                    delete_pair = True
                        except StopIteration:
                            iterator.finished = True
                if False not in [it.finished for it in it_pair]: return True
                if delete_pair:
                    iterators.remove(it_pair)
#                    if '' in license_file.path:
#                        logger.debug('Deleted {}'.format(it_pair))

        return bool(iterators)

    def _get_license_iterators(self, cachedfile, word):
        return [(cachedfile.iterator(loc), cachedfile.iterator(loc, backwards=True)) \
                for loc in cachedfile.get_locations(word)]


    def load_main_license(project):
        '''
        Load main license file for the project. It assigns it
        as Project's member
        '''
        names = map(re.compile, ['LICENSE', 'COPYRIGHT', 'COPYING'])

        for pfile in project.files:
            for name in names:
                if name.search(pfile.filename):
                    project.license_file = pfile
                    project.licenses = pfile.licenses
