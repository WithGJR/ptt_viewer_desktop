import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.0")
from gi.repository import Gtk, WebKit2, Gdk
import requests
from bs4 import BeautifulSoup
import http.server
import threading
import uuid
import os

def configure_cookies():
    jar = requests.cookies.RequestsCookieJar()
    jar.set('over18', '1', domain='www.ptt.cc', path='/')
    return jar

class PageSwitcher(Gtk.Stack):
    def __init__(self):
        super().__init__()
        self.set_homogeneous(False)
        self.pages = {}
        self.history = ["", ""] # stores current and previous page

    def add_page(self, page, name):
        self.add_named(page.get_widget(), name)
        self.pages[name] = page
        # when first page is added
        if self.history[0] == "":
            self.history[0] = name

    def update_history(self, name):
        self.history[1] = self.history[0]
        self.history[0] = name

    def change_page(self, name): 
        self.update_history(name)
        self.set_visible_child_name(name)   

    def go_back(self):
        prev_page_name = self.history[1]
        self.change_page(prev_page_name)

    def get_page(self, name):
        return self.pages[name]

class Page:
    def __init__(self, page_switcher):
        self.page_switcher = page_switcher

    def get_widget(self):
        pass

class HomePage(Page):
    def __init__(self, page_switcher):
        super().__init__(page_switcher)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)

        boards = self.fetch_board_list()
        for board in boards:
            row = Gtk.ListBoxRow()
            button = Gtk.Button(label=f"{board['name']} {board['class']}")
            button.connect("clicked", self.enter_post_list, board["url"])
            row.add(button)
            self.listbox.add(row)

    def enter_post_list(self, widget, url):
        post_list = self.page_switcher.get_page("post_list")
        post_list.set_url(url)
        post_list.render()
        self.page_switcher.change_page("post_list")

    def fetch_board_list(self):
        r = requests.get("https://www.ptt.cc/bbs/index.html")
        soup = BeautifulSoup(r.text, 'lxml')
        board_list = []
        for board in soup.find_all("a", class_="board"):
            board_dict = { 
                "url": f"https://www.ptt.cc{board['href']}",
                "name": board.find("div", class_="board-name").string,
                "class": board.find("div", class_="board-class").string
            }
            board_list.append(board_dict)
        return board_list

    def get_widget(self):
        return self.listbox


class PostListPage(Page):
    def __init__(self, page_switcher):
        super().__init__(page_switcher)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.prev = ""
        self.next = ""
    
    def set_url(self, url):
        self.url = url

    def goto_prev_page(self, widget):
        if self.prev == "":
            return
        self.set_url(self.prev)
        self.render()

    def goto_next_page(self, widget):
        if self.next == "":
            return
        self.set_url(self.next)
        self.render()

    def clear_children(self):
        for child in self.listbox.get_children():
            self.listbox.remove(child)

    def view_post(self, widget, url):
        if url == "":
            return

        post_page = self.page_switcher.get_page("post")
        post_page.set_url(url)
        post_page.render()
        self.page_switcher.change_page("post")

    def render(self):
        self.clear_children()
        post_list = self.fetch_post_list()
        self.prev = post_list["prev"]
        self.next = post_list["next"]
        row = Gtk.ListBoxRow()
        box = Gtk.Box(spacing=6, orientation=Gtk.Orientation.HORIZONTAL)
        prev_btn = Gtk.Button(label="Prev")
        prev_btn.connect("clicked", self.goto_prev_page)
        home_btn = Gtk.Button(label="Home")
        home_btn.connect("clicked", lambda widget: self.page_switcher.change_page("home"))
        next_btn = Gtk.Button(label="Next")
        next_btn.connect("clicked", self.goto_next_page)
        box.pack_start(prev_btn, True, True, 0)
        box.pack_start(home_btn, True, True, 0)
        box.pack_start(next_btn, True, True, 0)
        row.add(box)
        self.listbox.add(row)

        for post in post_list["list"]:
            row = Gtk.ListBoxRow()
            button = Gtk.Button(label=post["title"])
            button.connect("clicked", self.view_post, post["url"])
            row.add(button)
            self.listbox.add(row)
        self.listbox.show_all()    
    
    def fetch_post_list(self):
        r = requests.get(self.url, cookies=configure_cookies())
        soup = BeautifulSoup(r.text, "lxml")
        post_list = { "list": [] }
        for post in soup.find_all("div", class_="r-ent"):
            title = post.find("div", class_="title")
            post_dict = { 
                "title": title.a.string if title.a is not None else title.string.strip(),
                "url":  f"https://www.ptt.cc{title.a['href']}" if title.a is not None else ""
            }
            post_list["list"].append(post_dict)

        post_list["prev"] = soup.select(".btn-group-paging > a:nth-child(2)")[0]["href"] if "href" in soup.select(".btn-group-paging > a:nth-child(2)")[0].attrs else ""
        post_list["prev"] = f"https://www.ptt.cc{post_list['prev']}" if post_list["prev"] != "" else ""
        post_list["next"] = soup.select(".btn-group-paging > a:nth-child(3)")[0]["href"] if "href" in soup.select(".btn-group-paging > a:nth-child(3)")[0].attrs else ""
        post_list["next"] = f"https://www.ptt.cc{post_list['next']}" if post_list["next"] != "" else ""
        return post_list

    def get_widget(self):
        return self.listbox


class PostPage(Page):
    def __init__(self, page_switcher):
        super().__init__(page_switcher)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    def set_url(self, url):
        self.url = url
        
    def clear_children(self):
        for child in self.box.get_children():
            self.box.remove(child)

    def create_HTML_file(self, file, content):
        with open(file, "w") as f:
            f.write(content)

    def new_webview(self):
        settings = WebKit2.Settings()
        settings.set_enable_smooth_scrolling(True)
        settings.set_media_playback_allows_inline(True)
        settings.set_enable_javascript(True)
        settings.set_enable_javascript_markup(True)
        settings.set_enable_media(True)
        settings.set_enable_media_capabilities(True)
        settings.set_enable_mediasource(True)
        settings.set_enable_media_stream(True)
        settings.set_enable_encrypted_media(True)
        settings.set_auto_load_images(True)
        settings.set_allow_file_access_from_file_urls(True)
        settings.set_allow_universal_access_from_file_urls(True)
        settings.set_enable_hyperlink_auditing(True)
        settings.set_enable_html5_local_storage(True)
        settings.set_enable_html5_database(True)
        settings.set_enable_offline_web_application_cache(True)
        webview = WebKit2.WebView.new_with_settings(settings)
        bg_color = Gdk.RGBA()
        bg_color.parse("#000")
        webview.set_background_color(bg_color)
        return webview

    def render_richcontent(self, content):
        win = Gtk.ScrolledWindow()
        if content.find("youtube") != -1:
            win.set_min_content_height(200)
        else:
            win.set_min_content_height(500)
        
        webview = self.new_webview()
        filename = str(uuid.uuid4()) + ".html"
        self.create_HTML_file(f"./tmp/{filename}", "<html><body>" + content + "</body></html>")
        webview.load_uri(f"http://localhost:8000/{filename}")
        webview.show()
        win.add(webview)
        return win

    def render(self):
        self.clear_children()
        post = self.fetch_post()
        back_btn = Gtk.Button(label="Back")
        back_btn_context = back_btn.get_style_context()
        back_btn_context.add_class("back-button")
        back_btn.connect("clicked", lambda widget: self.page_switcher.go_back())
        self.box.add(back_btn)
        title = Gtk.Label(label=post["title"])
        self.box.pack_start(title, True, True, 0)
    
        for line in post["content"]:
            if isinstance(line, str):
                p = Gtk.Label(label=line.strip())
                p.set_halign(Gtk.Align.START)
                p.set_line_wrap(True)
                p.set_selectable(True)
            else:
                if ("class" in line.attrs) and ("richcontent" in line["class"]):
                    p = self.render_richcontent(str(line))    
                else:
                    p = Gtk.Label(label=line.get_text().strip())
                    p.set_halign(Gtk.Align.START)
                    p.set_line_wrap(True)
                    p.set_selectable(True)
            self.box.pack_start(p, True, True, 0)

        for comment in post["comments"]:
            if not comment["rich"]:
                p = Gtk.Label(label=f"{comment['user']} {comment['content']} {comment['time']}")
                p.set_halign(Gtk.Align.START)
                p.set_line_wrap(True)
                p.set_selectable(True)
            else:
                p = self.render_richcontent(str(comment))

            self.box.pack_start(p, True, True, 0)
        self.box.show_all()

    def get_comments(self, comment_str):
        # there are no comments
        if comment_str == "</div>":
            return []
        
        comment_tags = BeautifulSoup(comment_str.strip(), "lxml").body.children
        comments = []
        for comment in comment_tags:
            if isinstance(comment, str):
                c = { "user": "", "content": comment, "time": "", "rich": False }
            else:
                if "class" not in comment.attrs:
                    c = { "user": "", "content": "rich", "time": "time", "rich": True }
                elif "push" not in comment["class"]:
                    # richcontent
                    if "richcontent" in comment["class"]:
                        c = {"user": "", "content": str(comment), "time": "", "rich": True }
                    else:
                        c = {"user": "", "content": comment.get_text(), "time": "", "rich": False }
                else:
                    c = {
                       "user": comment.find("span", class_="push-userid").get_text().strip(),
                        "content": comment.find("span", class_="push-content").get_text(),
                        "time": comment.find("span", class_="push-ipdatetime").get_text(),
                        "rich": False
                    }
            comments.append(c)
        return comments

    def get_content(self, content_str):
        soup = BeautifulSoup(content_str, "lxml")
        for tag in soup.find_all("div", class_="article-metaline"):
            tag.extract()
        article_metaline_right = soup.find("div", class_="article-metaline-right")
        if article_metaline_right is not None:
            article_metaline_right.extract()
        return soup.find("div", id="main-content").children
        

    def fetch_post(self):
        r = requests.get(self.url, cookies=configure_cookies())
        soup = BeautifulSoup(r.text, "lxml")
        main_content = soup.find("div", id="main-content")
        post = {}
        post_meta = main_content.find_all("div", class_="article-metaline")
        post["title"] = post_meta[1].find("span", class_="article-meta-value").string if len(post_meta) > 0 else ""

        # find post link node  
        post_link = None
        for f2_node in main_content.find_all("span", class_="f2"):
            if f2_node.get_text().find("文章網址") != -1:
                post_link = f2_node
                break
        start = str(main_content).find(str(post_link))
        end = start + len(str(post_link))

        content_str = str(main_content)[:end]
        comment_str = str(main_content)[end:]
             
        post["content"] = self.get_content(content_str)
        post["comments"] = self.get_comments(comment_str)
        
        return post

    def get_widget(self):
        return self.box

win = Gtk.Window()
win.set_title("PTT Viewer")
win.set_default_size(500, 500)
win.set_border_width(10)
win.connect("destroy", Gtk.main_quit)

cssProvider = Gtk.CssProvider()
cssProvider.load_from_path("./style/screen.css")
screen = Gdk.Screen.get_default()
styleContext = Gtk.StyleContext()
styleContext.add_provider_for_screen(screen, cssProvider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

scrolled_win = Gtk.ScrolledWindow()
scrolled_win.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
page_switcher = PageSwitcher()
home = HomePage(page_switcher)
post_list = PostListPage(page_switcher)
post = PostPage(page_switcher)

page_switcher.add_page(home, "home")
page_switcher.add_page(post_list, "post_list")
page_switcher.add_page(post, "post")

scrolled_win.add(page_switcher)
win.add(scrolled_win)
win.show_all()

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="./tmp", **kwargs)

def serve():
    server = http.server.ThreadingHTTPServer(('', 8000), Handler)
    server.serve_forever()

t = threading.Thread(target = serve, daemon=True)
t.start()

def createDirectory(dir):
    try:
        os.mkdir(dir)
    except FileExistsError:
        pass

createDirectory("./tmp")

Gtk.main()