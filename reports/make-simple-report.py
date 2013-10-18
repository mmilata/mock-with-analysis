import codecs
import sys
import os
import os.path
import errno
import json
from collections import namedtuple

from reports import get_filename, ResultsDir, AnalysisIssue, Model, \
    Issue, SourceHighlighter, write_common_meta, write_common_css, \
    make_issue_note, make_failure_note, \
    write_issue_table_for_file, write_failure_table_for_file

class Backtrace(object):
    MatchResult = namedtuple('MatchResult',
                             ['frame_number', 'dist'])

    def __init__(self, backtrace_dict):
        self.bthash = backtrace_dict['hash']

        self.frames = []
        for frame_dict in backtrace_dict['frames']:
            self.frames.append(Frame(frame_dict))

    @property
    def url(self):
        return ('https://retrace.fedoraproject.org/faf/reports/bthash/%s'
                % self.bthash)

    def find_match(self, ai, dist_thresh=1):
        source = os.path.basename(ai.abspath)
        # frames are numbered from 1 in FAF
        for (n, frame) in enumerate(self.frames, 1):
            if frame.source_file is None or frame.source_file != source:
                continue

            # return the first/topmost match
            if frame.dist(ai) <= dist_thresh:
                return self.MatchResult(n, frame.dist(ai))

        return None

    def matches(self, ai):
        return (self.find_match(ai) != None)

class Frame(object):
    def __init__(self, frame_dict):
        if frame_dict['source_file'] is not None:
            self.source_file = os.path.basename(frame_dict['source_file'])
        else:
            self.source_file = None

        self.line_number = frame_dict['line_number']

    def dist(self, analysis):
        return abs(self.line_number - analysis.line)

class ModelWithCrashReports(Model):
    def __init__(self, rdir, report_file):
        Model.__init__(self, rdir)

        with open(report_file, 'r') as f:
            self.reports = json.load(f)

        # add backtraces attribute
        for analysis in self._analyses:
            for result in analysis.results:
                if isinstance(result, Issue):
                    result.backtraces = []

        self._correlate_reports()

    def _correlate_reports(self):

        # group backtraces by file
        bt_by_file = dict()
        for report in self.reports:
            #assert report['component'] == 'tracker'
            for bt_dict in report['backtraces']:
                backtrace = Backtrace(bt_dict)
                for frame in backtrace.frames:
                    bt_by_file.setdefault(frame.source_file, set()).add(backtrace)

        # correlate with analyses in same file
        for (file_, analyses) in self.get_analysis_issues_by_source().iteritems():
            source = os.path.basename(file_.abspath)

            try:
                backtraces = bt_by_file[source]
            except KeyError:
                continue

            for analysis in analyses:
                for backtrace in backtraces:
                    if backtrace.matches(analysis):
                        analysis.issue.backtraces.append(backtrace)


def write_html_header(f, sh, title=''):
    f.write('<html>\n')
    write_common_meta(f)
    f.write('<head><title>%s</title>\n' % title)

    f.write('    <style type="text/css">\n')

    write_common_css(f)

    f.write(sh.formatter.get_style_defs())

    f.write('      </style>\n')

    f.write('</head>\n')

    f.write('  <body>\n')

def write_html_footer(f):
    f.write('  </body>\n')
    f.write('</html>\n')

def write_source_report(code, file_, sh, ais_by_source, afs_by_source, f):
        f.write('<h2><a id="file-%s">%s</h2>\n' % (file_.hash_.hexdigest, get_filename(file_)))
        ais = ais_by_source.get(file_, set())
        if ais:
            write_issue_table_for_file(f, file_, ais)
        else:
            f.write('<p>No issues found</p>')
        afs = afs_by_source.get(file_, [])
        if afs:
            write_failure_table_for_file(f, file_, afs)

        # Write any lineless issues/failures at the start of the file:
        f.write('<a id="file-%s-line-0"/>' % (file_.hash_.hexdigest, ))
        for ai in ais:
            if ai.line is None:
                f.write(make_issue_note(ai))
        for af in afs:
            if af.line is None:
                f.write(make_failure_note(af))

        for i, line in enumerate(sh.highlight(code).splitlines()):
            f.write('<a id="file-%s-line-%i"/>' % (file_.hash_.hexdigest, i + 1))
            f.write(line)
            f.write('\n')
            for ai in ais:
                if ai.line == i + 1:
                    f.write(make_issue_note(ai))
            for af in afs:
                if af.line == i + 1:
                    f.write(make_failure_note(af))

def make_html(model, f):
    sh = SourceHighlighter()

    analyses = list(model.iter_analyses())

    write_html_header(f, sh)

    sources = model.get_source_files()
    generators = model.get_generators()
    ais_by_source = model.get_analysis_issues_by_source()
    ais_by_source_and_generator = model.get_analysis_issues_by_source_and_generator()
    afs_by_source = model.get_analysis_failures_by_source()

    sources_dir = 'sources'
    try:
        os.mkdir(sources_dir)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

    f.write('    <table>\n')
    if 1:
        f.write('    <tr>\n')
        f.write('      <th>Source file</th>\n')
        for generator in generators:
            f.write('      <th>%s</th>\n' % generator.name)
        f.write('      <th>Notes</th>\n')
        f.write('    </tr>\n')
    for file_ in sources:
        # skip this file if we don't have source
        try:
            source_html = file_.hash_.hexdigest + '.html'
            code = model.get_file_content(file_)
        except (IOError, AttributeError):
            continue

        # write table row
        f.write('    <tr>\n')
        f.write('      <td><a href="%s/%s">%s</a></td>\n'
                % (sources_dir, source_html, get_filename(file_)))
        for generator in generators:
            key = (file_, generator)
            ais = ais_by_source_and_generator.get(key, set())
            class_ = 'has_issues' if ais else 'no_issues'

            has_backtrace = ''
            if (isinstance(model, ModelWithCrashReports) and
                    any([bool(issue.issue.backtraces) for issue in ais])):
                has_backtrace = ' <span class="has_backtrace">BT</span>'

            f.write('      <td class="%s">%s%s</td>\n'
                    % (class_, len(ais), has_backtrace))

        afs = afs_by_source.get(file_, [])
        if afs:
            f.write('      <td>Incomplete coverage: %i analysis failure(s)</td>\n'
                    % len(afs))
        else:
            f.write('      <td></td>\n')
        f.write('    </tr>\n')

        # write the page with source code
        with codecs.open(os.path.join(sources_dir, source_html), encoding='utf-8', mode='w') as sf:
            write_html_header(sf, sh)
            write_source_report(code, file_, sh, ais_by_source, afs_by_source, sf)
            write_html_footer(sf)

    f.write('    </table>\n')

    write_html_footer(f)


def main(argv):
    path = argv[1]
    rdir = ResultsDir(path)
    if len(argv) < 3:
        model = Model(rdir)
    else:
        model = ModelWithCrashReports(rdir, argv[2]) # pass file object/parsed json?
    with codecs.open('index.html', encoding='utf-8', mode='w') as f:
        make_html(model, f)

main(sys.argv)

