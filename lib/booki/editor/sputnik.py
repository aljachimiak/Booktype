import redis, time
import simplejson

# must fix this rcon issue somehow. 
# this is stupid but will work for now

rcon = redis.Redis()
rcon.connect()

def hasChannel(channelName):
    global rcon

    return rcon.sismember("sputnik:channels", channelName)

def createChannel(channelName):
    global rcon

    if not hasChannel(channelName):
        rcon.sadd("sputnik:channels", channelName)

    return True

def removeChannel(channelName):
    global rcon

    return rcon.srem("sputnik:channels", channelName)

def addClientToChannel(channelName, client):
    global rcon

    rcon.sadd("ses:%s:channels" % client, channelName)

    rcon.sadd("sputnik:channel:%s:channel" % channelName, client)

def removeClientFromChannel(request, channelName, client):
    global rcon

    rcon.srem("sputnik:channel:%s:channel" % channelName, client)

    # get our username
    userName = rcon.get("ses:%s:username" % client)

    # get all usernames
    users = rcon.smembers("sputnik:channel:%s:users" % channelName)

    # get all clients
    allClients = []
    for cl in rcon.smembers("sputnik:channel:%s:channel" % channelName):
        allClients.append(rcon.get("ses:%s:username" % cl))

    for usr in users:
        if usr not in allClients:
            rcon.srem("sputnik:channel:%s:users" % channelName, usr)
            addMessageToChannel(request, channelName, {"command": "user_remove", "username": usr}, myself = True)


def addMessageToChannel(request, channelName, message, myself = False ):
    global rcon

    clnts = rcon.smembers("sputnik:channel:%s:channel" % channelName)

    message["channel"] = channelName
    message["clientID"] = request.clientID

    for c in clnts:
        if not myself and c == request.sputnikID:
            continue

        rcon.push( "ses:%s:messages" % c, simplejson.dumps(message), tail = True)

def removeClient(request, clientName):
    global rcon

    for chnl in rcon.smembers("ses:%s:channels" % clientName):
        removeClientFromChannel(request, chnl, clientName)
        rcon.srem("ses:%s:channels" % clientName, chnl)

    rcon.delete("ses:%s:username" % clientName)
    rcon.delete("ses:%s:last_access" % clientName)

    # TODO
    # also, i should delete all messages


## treba viditi shto opcenito sa onim

def booki_main(request, message):
    global rcon

#    rcon.connect()

    ret = {}
    if message["command"] == "ping":
        addMessageToChannel(request, "/booki/", {})

    if message["command"] == "disconnect":
        pass

    if message["command"] == "connect":
        # this is where we have problems when we get timeout
        def _getID():
            if not rcon.exists("sputnik:client_id"):
                rcon.set("sputnik:client_id", 0)
            
        try:
            _getID()
        except:
            rcon.connect()
            _getID()

        clientID = rcon.incr("sputnik:client_id")
        ret["clientID"] = clientID
        request.sputnikID = "%s:%s" % (request.session.session_key, clientID)

        # subscribe to this channels
        for chnl in message["channels"]:
            if not hasChannel(chnl):
                createChannel(chnl)

            addClientToChannel(chnl, request.sputnikID)

        # set our username
        rcon.set("ses:%s:username" % request.sputnikID, request.user.username)

        # set our last access
        rcon.set("ses:%s:last_access" % request.sputnikID, time.time())

    return ret



def booki_chat(request, message, bookid):
    if message["command"] == "message_send":
        addMessageToChannel(request, "/chat/%s/" % bookid, {"command": "message_received", "from": request.user.username, "message": message["message"]})
        return {}

    return {}

# remove all the copy+paste code


# getChapters

def getTOCForBook(book):
    from booki.editor import models

    results = []

    for chap in list(models.BookToc.objects.filter(book=book).order_by("-weight")):
        # is it a section or chapter
        if chap.chapter:
            results.append((chap.chapter.id, chap.chapter.title, chap.chapter.url_title, chap.typeof, chap.chapter.status.id))
        else:
            results.append(('s%s' % chap.id, chap.name, chap.name, chap.typeof))

    return results


# booki_book


def getHoldChapters(book_id):
    from django.db import connection, transaction
    cursor = connection.cursor()
    # wgere chapter_id is NULL that is the hold Chapter
    cursor.execute("select editor_chapter.id, editor_chapter.title, editor_chapter.url_title, editor_booktoc.chapter_id, editor_chapter.status_id from editor_chapter left outer join editor_booktoc on (editor_chapter.id=editor_booktoc.chapter_id)  where editor_chapter.book_id=%s;", (book_id, ))

    chapters = []
    for row in cursor.fetchall():
        if row[-2] == None:
            chapters.append((row[0], row[1], row[2], 1, row[4]))

    return chapters


def getAttachments(book):
    from booki.editor import models
    import os.path
    import Image

    def _getDimension(att):
        if att.attachment.name.endswith(".jpg"):
            try:
                im = Image.open(att.attachment.name)
                return im.size
            except:
                return (0, 0)
        return None
            

    attachments = [{"id": att.id, "dimension": _getDimension(att), "status": att.status.id, "name": os.path.split(att.attachment.name)[1], "size": att.attachment.size} for att in models.Attachment.objects.filter(book=book)]

    return attachments
    

def booki_book(request, message, bookid):
    from booki.editor import models

    ## init_editor
    if message["command"] == "init_editor":

        book = models.Book.objects.get(id=bookid)

        ## get chapters

        chapters = getTOCForBook(book)
        holdChapters =  getHoldChapters(bookid)

        ## get users

        def vidi(a):
            if a == request.sputnikID:
                return "<b>%s</b>" % a
            return a

        users = [vidi(m) for m in list(rcon.smembers("sputnik:channel:%s:channel" % message["channel"]))]

        ## get workflow statuses

        statuses = [(status.id, status.name) for status in models.BookStatus.objects.filter(book=book).order_by("-weight")]
        ## get attachments

        attachments = getAttachments(book)

        ## get metadata

        metadata = [{'name': v.name, 'value': v.getValue()} for v in models.Info.objects.filter(book=book)]

        ## notify others
        addMessageToChannel(request, "/chat/%s/" % bookid, {"command": "user_joined", "user_joined": request.user.username}, myself = False)

        ## get licenses

        licenses =  [(elem.abbrevation, elem.name) for elem in models.License.objects.all().order_by("name")]

        ## get online users
        onlineUsers = rcon.smembers("sputnik:channel:%s:users" % message["channel"])
        
        if request.user.username not in onlineUsers:
            rcon.sadd("sputnik:channel:%s:users" % message["channel"], request.user.username)
            onlineUsers.add(request.user.username)
  
            ## set notifications to other clients
            addMessageToChannel(request, "/booki/book/%s/" % bookid, {"command": "user_add", "username": request.user.username})
                
        return {"licenses": licenses, "chapters": chapters, "metadata": metadata, "hold": holdChapters, "users": users, "statuses": statuses, "attachments": attachments, "onlineUsers": list(onlineUsers)}

    ## attachments list
    if message["command"] == "attachments_list":
        book = models.Book.objects.get(id=bookid)

        attachments = getAttachments(book)

        return {"attachments": attachments}

    ## chapter_status
    if message["command"] == "chapter_status":
        addMessageToChannel(request, "/booki/book/%s/" % bookid, {"command": "chapter_status", "chapterID": message["chapterID"], "status": message["status"], "username": request.user.username})
        return {}

    ## chapter_save
    if message["command"] == "chapter_save":
        chapter = models.Chapter.objects.get(id=int(message["chapterID"]))
        chapter.content = message["content"];
        chapter.save()

        addMessageToChannel(request, "/chat/%s/" % bookid, {"command": "message_info", "from": request.user.username, "message": 'User %s has saved chapter "%s".' % (request.user.username, chapter.title)}, myself=True)

        addMessageToChannel(request, "/booki/book/%s/" % bookid, {"command": "chapter_status", "chapterID": message["chapterID"], "status": "normal", "username": request.user.username})

        return {}

    ## chapter_rename
    if message["command"] == "chapter_rename":
        chapter = models.Chapter.objects.get(id=int(message["chapterID"]))
        oldTitle = chapter.title
        chapter.title = message["chapter"];
        chapter.save()

        addMessageToChannel(request, "/chat/%s/" %  bookid, {"command": "message_info", "from": request.user.username, "message": 'User %s has renamed chapter "%s" to "%s".' % (request.user.username, oldTitle, message["chapter"])}, myself=True)

        addMessageToChannel(request, "/booki/book/%s/" % bookid, {"command": "chapter_status", "chapterID": message["chapterID"], "status": "normal", "username": request.user.username})
        addMessageToChannel(request, "/booki/book/%s/" % bookid, {"command": "chapter_rename", "chapterID": message["chapterID"], "chapter": message["chapter"]})
 
        return {}

    ## chapters_changed
    if message["command"] == "chapters_changed":
        lst = [chap[5:] for chap in message["chapters"]]
        lstHold = [chap[5:] for chap in message["hold"]]

        book = models.Book.objects.get(id=bookid)

        weight = len(lst)

        for chap in lst:
            if chap[0] == 's':
                m =  models.BookToc.objects.get(id__exact=int(chap[1:]))
                m.weight = weight
                m.save()
            else:
                try:
                    m =  models.BookToc.objects.get(chapter__id__exact=int(chap))
                    m.weight = weight
                    m.save()
                except:
                    chptr = models.Chapter.objects.get(id__exact=int(chap))
                    m = models.BookToc(book = book,
                                       name = "SOMETHING",
                                       chapter = chptr,
                                       weight = weight,
                                       typeof=1)
                    m.save()

            weight -= 1

        if message["kind"] == "remove":
            if type(message["chapter_id"]) == type(u' ') and message["chapter_id"][0] == 's':
                m =  models.BookToc.objects.get(id__exact=message["chapter_id"][1:])
                m.delete()
            else:
                m =  models.BookToc.objects.get(chapter__id__exact=int(message["chapter_id"]))
                m.delete()

#        addMessageToChannel(request, "/chat/%s/%s/" % (projectid, bookid), {"command": "message_info", "from": request.user.username, "message": 'User %s has rearranged chapters.' % request.user.username})

        addMessageToChannel(request, "/booki/book/%s/" % bookid, {"command": "chapters_changed", "ids": lst, "hold_ids": lstHold, "kind": message["kind"], "chapter_id": message["chapter_id"]})
        return {}

    ## get_users
    if message["command"] == "get_users":
        res = {}
        def vidi(a):
            if a == request.sputnikID:
                return "!%s!" % a
            return a

        res["users"] = [vidi(m) for m in list(rcon.smembers("sputnik:channel:%s:channel" % message["channel"]))]
        return res 

    ## get_chapter
    if message["command"] == "get_chapter":
        res = {}

        chapter = models.Chapter.objects.get(id=int(message["chapterID"]))
        res["title"] = chapter.title
        res["content"] = chapter.content 

        addMessageToChannel(request, "/booki/book/%s/" % bookid, {"command": "chapter_status", "chapterID": message["chapterID"], "status": "edit", "username": request.user.username})

        return res

    ## chapter_split
    if message["command"] == "chapter_split":
        book = models.Book.objects.get(id=bookid)

        allChapters = []

        try:
            originalChapter = models.Chapter.objects.get(id=int(message["chapterID"]))
        except:
            originalChapter = None
        
        try:
            tocChapter = models.BookToc.objects.get(book=book, chapter__id__exact=message["chapterID"])
        except:
            tocChapter = None

        import datetime
        from django.template.defaultfilters import slugify

        if tocChapter:
            allChapters = [chap for chap in models.BookToc.objects.filter(book=book).order_by("-weight")]
            initialPosition =  len(allChapters)-tocChapter.weight
        else:
            initialPosition = 0

        s = models.BookStatus.objects.filter(book=book).order_by("weight")[0]

        n = 0
        for chap in message["chapters"]:
            chapter = models.Chapter(book = book,
                                     url_title = slugify(chap[0]),
                                     title = chap[0],
                                     status = s,
                                     content = '<h1>%s</h1>%s' % (chap[0], chap[1]),
                                     created = datetime.datetime.now(),
                                     modified = datetime.datetime.now())
            chapter.save()

            if tocChapter:
                m = models.BookToc(book = book,
                                   chapter = chapter,
                                   name = chap[0],
                                   weight = 0,
                                   typeof = 1)
                m.save()
                allChapters.insert(1+initialPosition+n, m)

            n += 1

        if originalChapter:
            addMessageToChannel(request, "/chat/%s/" % bookid, {"command": "message_info", "from": request.user.username, "message": 'User %s has split chapter "%s".' % (request.user.username, originalChapter.title)}, myself=True)

            originalChapter.delete()

        if tocChapter:
            tocChapter.delete()

        n = len(allChapters)
        for chap in allChapters:
            try:
                chap.weight = n
                chap.save()
                n -= 1
            except:
                pass

        ## get chapters

        chapters = getTOCForBook(book)
        holdChapters =  getHoldChapters(bookid)
        
        addMessageToChannel(request, "/booki/book/%s/" % bookid, {"command": "chapter_split", "chapterID": message["chapterID"], "chapters": chapters, "hold": holdChapters, "username": request.user.username}, myself = True)

            
        return {}

    ## create_chapter
    if message["command"] == "create_chapter":
        from booki.editor import models

        import datetime

        book = models.Book.objects.get(id=bookid)

        from django.template.defaultfilters import slugify

        url_title = slugify(message["chapter"])

        # here i should probably set it to default project status
        s = models.BookStatus.objects.filter(book=book).order_by("weight")[0]

        chapter = models.Chapter(book = book,
                                 url_title = url_title,
                                 title = message["chapter"],
                                 status = s,
                                 content = '<h1>%s</h1>' % message["chapter"],
                                 created = datetime.datetime.now(),
                                 modified = datetime.datetime.now())
        chapter.save()

        result = (chapter.id, chapter.title, chapter.url_title, 1, s.id)

        addMessageToChannel(request, "/chat/%s/" % bookid, {"command": "message_info", "from": request.user.username, "message": 'User %s has created new chapter "%s".' % (request.user.username, message["chapter"])}, myself=True)


        addMessageToChannel(request, "/booki/book/%s/" % bookid, {"command": "chapter_create", "chapter": result}, myself = True)

        return {}

    ## publish_book
    if message["command"] == "publish_book":
        book = models.Book.objects.get(id=bookid)

        addMessageToChannel(request, "/chat/%s/" % bookid, {"command": "message_info", "from": request.user.username, "message": '"%s" is being published.' % (book.title, )}, myself=True)

        import urllib2
        urlPublish = "http://objavi.flossmanuals.net/objavi.cgi"
#        urlPublish = "http://objavi.halo.gen.nz/objavi.cgi"

        publishMode = message.get("publish_mode", "epub")
        destination = "nowhere"

        if message.get("is_archive", False):
            destination = "archive.org"

            
        # TODO
        # change project here
#        f = urllib2.urlopen("%s?book=%s&project=%s&mode=%s&server=booki.flossmanuals.net&destination=%s" % (urlPublish, book.url_title, project.url_name, publishMode, destination))
#        ta = f.read()
#        lst = ta.split("\n")
#        dta, dtas3 = "", ""

#        if len(lst) > 0:
#            dta = lst[0]

#            if len(lst) > 1:
#                dtas3 = lst[1]

#        addMessageToChannel(request, "/chat/%s/" % bookid, {"command": "message_info", "from": request.user.username, "message": '"%s" is published.' % (book.title, )}, myself=True)
        ta , dta, dta3 = "", "", ""
        return {"dtaall": ta, "dta": dta, "dtas3": dtas3}

    ## create_section
    if message["command"] == "create_section":
        from booki.editor import models

        import datetime
        book = models.Book.objects.get(id=bookid)

        c = models.BookToc(book = book,
                           name = message["chapter"],
                           chapter = None,
                           weight = 0,
                           typeof=0)
        c.save()

        result = ("s%s" % c.id, c.name, None, c.typeof)


        addMessageToChannel(request, "/chat/%s/" % bookid, {"command": "message_info", "from": request.user.username, "message": 'User %s has created new section "%s".' % (request.user.username, message["chapter"])}, myself=True)

        addMessageToChannel(request, "/booki/book/%s/" %  bookid, {"command": "chapter_create", "chapter": result, "typeof": c.typeof}, myself = True)

        return {}


    return {}
