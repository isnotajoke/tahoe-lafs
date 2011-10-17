
import simplejson
from nevow import rend, tags as T, inevow
from allmydata.web.common import getxmlfile, abbreviate_time, get_arg
from allmydata.util.abbreviate import abbreviate_space
from allmydata.util import base32
from twisted.web import resource, static

def remove_prefix(s, prefix):
    if not s.startswith(prefix):
        return None
    return s[len(prefix):]

import re

class Storage(resource.Resource):
    isLeaf = True
    def __init__(self, storage):
        resource.Resource.__init__(self)
        self.storage = storage

    def getChild(self, path, req):
        print "GETCHILD", path, req.postpath
        pieces = req.postpath.split("/")
        assert path == "SI"
        si = base32.a2b(pieces[0])
        assert pieces[1] == "share"
        shnum = int(pieces[2])
        r = req.getHeader("range")
        assert r.startswith("bytes=")
        mo = re.search(r'=(\d+)-(\d+)$')
        first,last = int(mo.group(1)), int(mo.group(2))
        length = last-first+1
        data = self.storage.get_immutable_data(si, shnum, first, length)
        return static.Data(data, "text/plain")

class StorageStatus(rend.Page):
    docFactory = getxmlfile("storage_status.xhtml")
    # the default 'data' argument is the StorageServer instance

    def __init__(self, storage):
        rend.Page.__init__(self, storage)
        self.storage = storage
        self.child_imm = Storage(self.storage)

    def renderHTTP(self, ctx):
        print "HEASDS"
        req = inevow.IRequest(ctx)
        t = get_arg(req, "t")
        if t == "json":
            return self.render_JSON(req)
        return rend.Page.renderHTTP(self, ctx)

    def render_JSON(self, req):
        req.setHeader("content-type", "text/plain")
        d = {"stats": self.storage.get_stats(),
             "bucket-counter": self.storage.bucket_counter.get_state(),
             }
        return simplejson.dumps(d, indent=1) + "\n"

    def render_storage_running(self, ctx, storage):
        if storage:
            return ctx.tag
        else:
            return T.h1["No Storage Server Running"]

    def render_bool(self, ctx, data):
        return {True: "Yes", False: "No"}[bool(data)]

    def render_abbrev_space(self, ctx, size):
        if size is None:
            return "?"
        return abbreviate_space(size)

    def render_space(self, ctx, size):
        if size is None:
            return "?"
        return "%d" % size

    def data_stats(self, ctx, data):
        # FYI: 'data' appears to be self, rather than the StorageServer
        # object in self.original that gets passed to render_* methods. I
        # still don't understand Nevow.

        # Nevow has nevow.accessors.DictionaryContainer: Any data= directive
        # that appears in a context in which the current data is a dictionary
        # will be looked up as keys in that dictionary. So if data_stats()
        # returns a dictionary, then we can use something like this:
        #
        #  <ul n:data="stats">
        #   <li>disk_total: <span n:render="abbrev" n:data="disk_total" /></li>
        #  </ul>

        # to use get_stats()["storage_server.disk_total"] . However,
        # DictionaryContainer does a raw d[] instead of d.get(), so any
        # missing keys will cause an error, even if the renderer can tolerate
        # None values. To overcome this, we either need a dict-like object
        # that always returns None for unknown keys, or we must pre-populate
        # our dict with those missing keys, or we should get rid of data_
        # methods that return dicts (or find some way to override Nevow's
        # handling of dictionaries).

        d = dict([ (remove_prefix(k, "storage_server."), v)
                   for k,v in self.storage.get_stats().items() ])
        d.setdefault("disk_total", None)
        d.setdefault("disk_used", None)
        d.setdefault("disk_free_for_root", None)
        d.setdefault("disk_free_for_nonroot", None)
        d.setdefault("reserved_space", None)
        d.setdefault("disk_avail", None)
        return d

    def data_last_complete_bucket_count(self, ctx, data):
        s = self.storage.bucket_counter.get_state()
        count = s.get("last-complete-bucket-count")
        if count is None:
            return "Not computed yet"
        return count

    def render_count_crawler_status(self, ctx, storage):
        p = self.storage.bucket_counter.get_progress()
        return ctx.tag[self.format_crawler_progress(p)]

    def format_crawler_progress(self, p):
        cycletime = p["estimated-time-per-cycle"]
        cycletime_s = ""
        if cycletime is not None:
            cycletime_s = " (estimated cycle time %s)" % abbreviate_time(cycletime)

        if p["cycle-in-progress"]:
            pct = p["cycle-complete-percentage"]
            soon = p["remaining-sleep-time"]

            eta = p["estimated-cycle-complete-time-left"]
            eta_s = ""
            if eta is not None:
                eta_s = " (ETA %ds)" % eta

            return ["Current crawl %.1f%% complete" % pct,
                    eta_s,
                    " (next work in %s)" % abbreviate_time(soon),
                    cycletime_s,
                    ]
        else:
            soon = p["remaining-wait-time"]
            return ["Next crawl in %s" % abbreviate_time(soon),
                    cycletime_s]
