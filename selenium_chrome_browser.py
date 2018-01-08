import logging

from selenium import webdriver

from abc_browser import ABCBrowser


class SeleniumChromeBrowser(ABCBrowser):
    chromedriver = None

    def __init__(self, **kvargs):
        """
        Initialize ChromeDriver
        :param kvargs: headless, disable_images, width, height, implicitly_wait
        """
        # Configuring Chrome
        chrome_options = webdriver.ChromeOptions()
        if kvargs.get('headless', False):
            # Headless mode works only for Chrome 60+ (on Windows)
            chrome_options.add_argument('headless')
            chrome_options.add_argument(f'window-size={kvargs.get("width", 1920)}x{kvargs.get("height", 1080)}')

        if kvargs.get('disable_images', False):
            chrome_options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})

        self.chromedriver = webdriver.Chrome(chrome_options=chrome_options)
        self.chromedriver.implicitly_wait(kvargs.get('implicitly_wait', 1))

        # TODO: Stopped working. selenium.common.exceptions.WebDriverException: Message: disconnected: unable to connect to renderer
        # if headless is False:
        #     sleep(1)
        #     self.chromedriver.set_window_size(width, height)

        logging.debug('ChromeDriver has been initialized')
        super().__init__(**kvargs)

    def __del__(self):
        if self.chromedriver is not None:
            self.chromedriver.close()

    def get(self, url):
        return self.chromedriver.get(url)

    def find_elements_by_xpath(self, xpath, web_element=None):
        if web_element is None:
            return self.chromedriver.find_elements_by_xpath(xpath)
        else:
            return web_element.find_elements_by_xpath(xpath)

    def get_element_attribute(self, element, attribute):
        return element.get_attribute(attribute)

    def scroll_to_element(self, element):
        self.chromedriver.execute_script("""var viewPortHeight = Math.max(document.documentElement.clientHeight, window.innerHeight || 0);
                                            var elementTop = arguments[0].getBoundingClientRect().top;
                                            window.scrollBy(0, elementTop-(viewPortHeight/2));""", element)

    def get_current_page_as_element(self):
        return self.chromedriver
