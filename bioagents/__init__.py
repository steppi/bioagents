import sys
import logging
logging.basicConfig(format='%(levelname)s: %(name)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger('Bioagents')
from itertools import groupby
from collections import defaultdict
from indra.assemblers import EnglishAssembler
from kqml import KQMLModule, KQMLPerformative, KQMLList


class BioagentException(Exception):
    pass


class Bioagent(KQMLModule):
    """Abstract class for bioagents."""
    name = "Generic Bioagent (Should probably be overwritten)"
    tasks = []

    def __init__(self, **kwargs):
        super(Bioagent, self).__init__(name=self.name, **kwargs)
        for task in self.tasks:
            self.subscribe_request(task)

        self.ready()
        self.start()
        logger.info("%s is has started and ready." % self.name)
        return

    def receive_request(self, msg, content):
        """Handle request messages and respond.

        If a "request" message is received, decode the task and the content
        and call the appropriate function to prepare the response. A reply
        message is then sent back.
        """
        try:
            content = msg.get('content')
            task = content.head().upper()
        except Exception as e:
            logger.error('Could not get task string from request.')
            logger.error(e)
            reply_content = self.make_failure('INVALID_REQUEST')
            return self.reply_with_content(msg, reply_content)

        if task in self.tasks:
            reply_content = self._respond_to(task, content)
        else:
            logger.error('Could not perform task.')
            logger.error("Task %s not found in %s." %
                         (task, str(self.tasks)))
            reply_content = self.make_failure('UNKNOWN_TASK')

        return self.reply_with_content(msg, reply_content)

    def _respond_to(self, task, content):
        """Get the method to responsd to the task indicated by task."""
        resp_name = "respond_" + task.replace('-', '_').lower()
        try:
            resp = getattr(self, resp_name)
        except AttributeError:
            logger.error("Tried to execute unimplemented task.")
            logger.error("Did not find response method %s." % resp_name)
            return self.make_failure('INVALID_TASK')
        try:
            reply_content = resp(content)
            return reply_content
        except BioagentException:
            raise
        except Exception as e:
            logger.error('Could not perform response to %s' % task)
            logger.exception(e)
            return self.make_failure('INTERNAL_FAILURE')

    def reply_with_content(self, msg, reply_content):
        """A wrapper around the reply method from KQMLModule."""
        reply_msg = KQMLPerformative('reply')
        reply_msg.set('content', reply_content)
        self.reply(msg, reply_msg)
        return (msg, reply_content)

    def tell(self, content):
        """Send a tell message."""
        msg = KQMLPerformative('tell')
        msg.set('content', content)
        return self.send(msg)

    def error_reply(self, msg, comment):
        if not self.testing:
            return KQMLModule.error_reply(self, msg, comment)
        else:
            return (msg, comment)

    def make_failure(self, reason=None, description=None):
        msg = KQMLList('FAILURE')
        if reason:
            msg.set('reason', reason)
        if description:
            msg.sets('description', description)
        return msg

    def send_provenance_for_stmts(self, stmt_list, for_what, limit=5):
        """Send out a provenance tell for a list of INDRA Statements.

        The message is used to provide evidence supporting a conclusion.
        """
        content_fmt = ('<h4>Supporting evidence from the {bioagent} for '
                       '{conclusion}:</h4>\n{evidence}<hr>')
        evidence_html = make_evidence_html(stmt_list, for_what, limit)
        # Actually create the content.
        content = KQMLList('add-provenance')
        content.sets('html',
                     content_fmt.format(conclusion=for_what,
                                        evidence=evidence_html,
                                        bioagent=self.name))
        return self.tell(content)

def make_evidence_html(stmt_list, for_what, limit=5):
    """Creates HTML content for evidences corresponding to INDRA Statements."""
    # Create some formats
    url_base = 'https://www.ncbi.nlm.nih.gov/pubmed/'
    pmid_link_fmt = '<a href={url}{pmid} target="_blank">PMID{pmid}</a>'
    # Extract a list of the evidence then map pmids to lists of text
    evidence_lst = [ev for stmt in stmt_list for ev in stmt.evidence]
    pmid_groups = groupby(evidence_lst, lambda x: x.pmid)
    pmid_text_dict = defaultdict(set)
    for pmid, evidences in pmid_groups:
        for ev in evidences:
            # If the entry has proper text evidence
            if ev.text:
                entry = "<i>\'%s\'</i>" % ev.text
            # If the entry at least has a source ID in a database
            elif ev.source_id:
                entry = "Database entry in '%s': %s" % \
                    (ev.source_api, ev.source_id)
            # Otherwise turn it into English
            else:
                txt = EnglishAssembler([stmt]).make_model()
                entry = "Evidence from '%s': %s" % (ev.source_api, txt)
            pmid_text_dict[pmid].add(entry)
    # Create the text for displaying the evidence.
    stmt_ev_fmt = ('Found in ' + pmid_link_fmt + ':\n<ul>{evidence}</ul>')
    evidence_text_list = []
    def evidence_list(txt_list):
        # Add a list item for each piece of text
        return '\n'.join(['<li>%s</li>' % txt.encode('utf-8')
                          for txt in txt_list])
    entries = [stmt_ev_fmt.format(url=url_base,
                                  pmid=pmid,
                                  evidence=evidence_list(txt_list))
               for pmid, txt_list in pmid_text_dict.items()]
    evidence_text_list.append('\n'.join(entries))
    evidence_html = 'and...\n'.join(evidence_text_list)
    return evidence_html
