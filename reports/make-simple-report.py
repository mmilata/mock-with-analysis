import codecs
import sys
import os
import errno

from reports import get_filename, ResultsDir, AnalysisIssue, Model, \
    SourceHighlighter, write_common_meta, write_common_css, \
    make_issue_note, make_failure_note, \
    write_issue_table_for_file, write_failure_table_for_file

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
            f.write('      <td class="%s">%s</td>\n' % (class_, len(ais)))
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
    model = Model(rdir)
    with codecs.open('index.html', encoding='utf-8', mode='w') as f:
        make_html(model, f)

main(sys.argv)

