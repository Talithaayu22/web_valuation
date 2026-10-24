from html.parser import HTMLParser
import sys

class StrictHTMLValidator(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.void_tags = {"meta", "link", "img", "br", "hr", "input", "col", "area", "base"}

    def handle_starttag(self, tag, attrs):
        if tag not in self.void_tags:
            self.tags.append(tag)

    def handle_endtag(self, tag):
        if tag not in self.void_tags:
            if not self.tags:
                print(f"Error: Unexpected closing tag </{tag}>")
                sys.exit(1)
            last = self.tags.pop()
            if last != tag:
                print(f"Error: Mismatched tag. Expected </{last}>, found </{tag}>")
                sys.exit(1)

def validate():
    validator = StrictHTMLValidator()
    with open("standalone_mockup/idx_valuation_workspace.html", "r", encoding="utf-8") as f:
        content = f.read()
    validator.feed(content)
    if validator.tags:
        print(f"Warning: Unclosed tags remaining: {validator.tags}")
        sys.exit(1)
    print("HTML validation passed! All tags properly closed and matched.")

if __name__ == "__main__":
    validate()
