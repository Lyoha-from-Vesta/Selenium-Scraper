import json
import logging
import re
from datetime import datetime
from time import sleep
from urllib.parse import urljoin
import xlsxwriter as xlsxwriter
from selenium import webdriver
from selenium.common.exceptions import WebDriverException


def is_none_or_empty(string: str) -> bool:
    return bool(string is None or not (string.strip()))


class Scraper(object):
    browser = None
    config = None

    class UrlTypes(object):
        CATALOGUE = 0
        PRODUCT = 1

    t_links_work = dict()
    t_links_work_pk = set()

    t_products_work = dict()
    t_products_work_pk = set()

    t_product_variants_work = dict()
    t_product_variants_work_pk = set()

    t_product_variant_images_work = dict()
    t_product_variant_images_work_pk = set()

    def __init__(self, config: dict, headless=False, disable_images=False, width=1920, height=1080, implicitly_wait=5):
        self.config = config
        self.init_chrome_driver(headless, disable_images, width, height, implicitly_wait)

    def __del__(self):
        self.browser.close()

    def init_chrome_driver(self, headless: bool, disable_images: bool, width: int, height: int, implicitly_wait: int):
        # Configuring Chrome
        chrome_options = webdriver.ChromeOptions()
        if headless:
            # Headless mode works only for Chrome 60+ (on Windows)
            chrome_options.add_argument('headless')
            chrome_options.add_argument(f'window-size={width}x{height}')

        if disable_images:
            chrome_options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})

        self.browser = webdriver.Chrome(chrome_options=chrome_options)
        self.browser.implicitly_wait(implicitly_wait)

        if not headless:
            self.browser.set_window_size(width, height)

        logging.debug('ChromeDriver has been initialized')

    def scrape(self, get_interval=1.00):
        self.put_initial_url(self.UrlTypes.CATALOGUE)

        url_to_scrape = self.get_next_url_to_scrape()
        while url_to_scrape:
            self.scrape_url(url_to_scrape)
            url_to_scrape = self.get_next_url_to_scrape()
            sleep(get_interval)

    def save_results_to_xslx(self, report_file_name: str):
        # Create a workbook and add a worksheet.
        workbook_name = self.config['website_name'] or "Scraping Results"
        workbook = xlsxwriter.Workbook(f"{workbook_name.replace(' ', '_')}.xlsx")
        worksheet = workbook.add_worksheet(name=workbook_name)

        # Add a bold format to use to highlight row headers.
        bold_format = workbook.add_format({'bold': True})

        # Write data headers.
        worksheet.write('A1', 'name', bold_format)
        worksheet.write('B1', 'sku', bold_format)
        worksheet.write('C1', 'description', bold_format)
        worksheet.write('D1', 'category_1', bold_format)
        worksheet.write('E1', 'category_2', bold_format)
        worksheet.write('F1', 'category_3', bold_format)
        worksheet.write('G1', 'url', bold_format)
        worksheet.write('H1', 'image_url', bold_format)

        # Writing data
        row = 1
        for product_key in self.t_products_work.keys():
            product = self.t_products_work[product_key]
            variants = self.select_variants_where_product_key(product_key)
            for variant in variants:
                image_url = self.select_image_url_where_variant_id(variant['record_id'])
                worksheet.write(row, 0, product['name'])
                worksheet.write(row, 1, variant['sku'])
                worksheet.write(row, 2, product['description'])
                worksheet.write(row, 3, product['category_1'])
                worksheet.write(row, 4, product['category_2'])
                worksheet.write(row, 5, product['category_3'])
                worksheet.write(row, 6, product['url'])
                worksheet.write(row, 7, image_url)
                row += 1

        workbook.close()
        logging.info(f"Export to Excel file {workbook_name} is finished. Rows saved: {row - 1}")


    def put_initial_url(self, url_type: int):
        self.t_links_work_pk.add((self.config['initial_url'], url_type))
        self.t_links_work[0] = {'url': self.config['initial_url'],
                                'url_type_id': url_type,
                                'retrieved': None,
                                'record_id': 0}

    def get_next_url_to_scrape(self) -> dict or None:
        for rid in self.t_links_work.keys():
            if self.t_links_work[rid]['retrieved'] is None:
                return self.t_links_work[rid]
        return None

    def insert_t_links_work(self, url: str, url_type_id: int):
        if (url, url_type_id) not in self.t_links_work_pk:
            self.t_links_work_pk.add((url, url_type_id))
            record_id = len(self.t_links_work)
            self.t_links_work[record_id] = {'url': url,
                                            'url_type_id': url_type_id,
                                            'retrieved': None,
                                            'record_id': record_id}

    def insert_t_products_work(self, name: str, description: str or None, category_1: str or None,
                               category_2: str or None, category_3: str or None, url: str) -> int or None:
        if url not in self.t_products_work_pk:
            self.t_products_work_pk.add(url)
            record_id = len(self.t_products_work)
            self.t_products_work[record_id] = {'name': name,
                                               'description': description,
                                               'category_1': category_1,
                                               'category_2': category_2,
                                               'category_3': category_3,
                                               'url': url,
                                               'record_id': record_id}
            return record_id
        else:
            return None

    def insert_t_product_variants_work(self, variant_sku, product_record_id):
        if (variant_sku, product_record_id) not in self.t_product_variants_work_pk:
            self.t_product_variants_work_pk.add((variant_sku, product_record_id))
            record_id = len(self.t_product_variants_work)
            self.t_product_variants_work[record_id] = {'sku': variant_sku,
                                                       'product_record_id': product_record_id,
                                                       'record_id': record_id}
            return record_id
        else:
            return None

    def insert_t_product_variant_images_work(self, url, variant_id):
        if (url, variant_id) not in self.t_product_variant_images_work_pk:
            self.t_product_variant_images_work_pk.add((url, variant_id))
            record_id = len(self.t_product_variant_images_work)
            self.t_product_variant_images_work[record_id] = {'url': url,
                                                             'variant_id': variant_id,
                                                             'record_id': record_id}
            return record_id
        else:
            return None

    def scrape_url(self, url_to_scrape: dict):
        # If the URL is a catalogue - get links
        if url_to_scrape['url_type_id'] == self.UrlTypes.CATALOGUE:
            logging.debug(f'Scraping catalogue URL: {url_to_scrape["url"]}')
            self.extract_links(url_to_scrape)
        else:  # If the URL is a product - get product data and variants
            logging.debug(f'Scraping product URL: {url_to_scrape["url"]}')
            self.extract_product_data(url_to_scrape)

        self.t_links_work[url_to_scrape['record_id']]['retrieved'] = datetime.now()

    def extract_links(self, url_to_scrape):
        self.browser.get(url_to_scrape['url'])

        # TODO: Here we need to click a button while it exists. Should create a corresponding option in config.
        clicks = 0
        button_load_more_xpath = '//button[@class="round loadMore"]'
        button_load_more = self.browser.find_elements_by_xpath(button_load_more_xpath)
        while len(button_load_more):
            # webdriver.ActionChains(self.browser).move_to_element(button_load_more[0]).perform()
            self.browser.execute_script("arguments[0].scrollIntoView();", button_load_more[0])
            button_load_more[0].click()
            clicks += 1
            button_load_more = self.browser.find_elements_by_xpath(button_load_more_xpath)
            if clicks > 10:
                logging.warning(f"Too many clicks on page {url_to_scrape['url']}, selector: {button_load_more_xpath}")
                break

        # Extracting links from the page
        extracted_links = set()
        catalogue_url_regex_filters = list()
        for cre in self.config['config_links']['links']['regexps']:  # TODO: rename links to catalogues in config?
            try:
                catalogue_url_regex_filters.append(re.compile(cre))
            except:
                logging.error(f'Invalid catalogue regex: {cre}')

        product_url_regex_filters = list()
        for pre in self.config['config_links']['products']['regexps']:
            try:
                product_url_regex_filters.append(re.compile(pre))
            except:
                logging.error(f'Invalid product regex: {pre}')

        for catalogue_xpath in self.config['config_links']['links']['xpaths']:
            for a_element in self.browser.find_elements_by_xpath(catalogue_xpath):
                catalogue_url = urljoin(url_to_scrape['url'], a_element.get_attribute('href'))
                if len(catalogue_url_regex_filters) and not (
                        any(regex.match(catalogue_url) for regex in catalogue_url_regex_filters)):
                    continue
                extracted_links.add((catalogue_url, self.UrlTypes.CATALOGUE))

        for product_xpath in self.config['config_links']['products']['xpaths']:
            for a_element in self.browser.find_elements_by_xpath(product_xpath):
                product_url = urljoin(url_to_scrape['url'], a_element.get_attribute('href'))
                if len(product_url_regex_filters) and not (
                        any(regex.match(product_url) for regex in product_url_regex_filters)):
                    continue
                extracted_links.add((product_url, self.UrlTypes.PRODUCT))

        # logging.debug(f'Adding new links to DB: {extracted_links}')
        for (url, link_type) in extracted_links:
            self.insert_t_links_work(url, link_type)

    def extract_product_data(self, url_to_scrape):
        self.browser.get(url_to_scrape['url'])

        # Getting product data
        product_name = self.get_web_element_attribute(self.config['config_products']['product_selectors']['name']['sel'])
        product_description = self.get_web_element_attribute(
            self.config['config_products']['product_selectors']['description']['sel'])
        product_category1 = self.get_web_element_attribute(
            self.config['config_products']['product_selectors']['category1']['sel'])
        product_category2 = self.get_web_element_attribute(
            self.config['config_products']['product_selectors']['category2']['sel'])
        product_category3 = self.get_web_element_attribute(
            self.config['config_products']['product_selectors']['category3']['sel'])

        # Validating products data
        if not product_name:
            logging.warning(
                f"Unable to extract product name! This product will be skipped. URL: {url_to_scrape['url']}, selector: {self.config['config_products']['product_selectors']['name']['sel']}")
            return
        if is_none_or_empty(product_description):
            logging.warning(
                f"Product '{product_name}' has no description! URL: {url_to_scrape['url']}, selector: {self.config['config_products']['product_selectors']['description']['sel']}")
        if is_none_or_empty(product_category1) and is_none_or_empty(product_category2) and is_none_or_empty(
                product_category3):
            logging.warning(f"Product '{product_name}' has no categories! URL: {url_to_scrape['url']}")

        new_product_record_id = self.insert_t_products_work(product_name, product_description, product_category1,
                                                            product_category2, product_category3, url_to_scrape['url'])
        logging.debug(f'Extracted product: {product_name}')

        # Getting a list of variants for the product
        continue_scraping = bool(new_product_record_id is not None)
        clicks = 0
        while continue_scraping:
            product_variants = self.browser.find_elements_by_xpath(
                self.config['config_products']['variant_settings']['sel'])

            if not len(product_variants):
                logging.warning(f"Product '{product_name}' has no wariants! URL: {url_to_scrape['url']}, selector: {self.config['config_products']['variant_settings']['sel']}")
                return

            for variant in product_variants:
                variant_sku = self.get_web_element_attribute(
                    self.config['config_products']['variant_settings']['product_code'],
                    variant)

                if is_none_or_empty(variant_sku):
                    logging.warning(f"Variant of product '{product_name}' has no SKU! URL: {url_to_scrape['url']}, selector: {self.config['config_products']['variant_settings']['sel']} + {self.config['config_products']['variant_settings']['product_code']}")
                    continue

                new_product_variant_id = self.insert_t_product_variants_work(variant_sku, new_product_record_id)
                logging.debug(f'\tVariant: {variant_sku}')

                if new_product_variant_id is not None:
                    variant_image_url = self.get_web_element_attribute(
                        self.config['config_products']['product_selectors']['image_file_name_1']['sel'],
                        variant)

                    if is_none_or_empty(variant_image_url):
                        logging.warning(
                            f"Variant of product '{product_name}' has no image! URL: {url_to_scrape['url']}, selector: {self.config['config_products']['variant_settings']['sel']} + {self.config['config_products']['product_selectors']['image_file_name_1']['sel']}")
                        return

                    self.insert_t_product_variant_images_work(variant_image_url, new_product_variant_id)
                    logging.debug(f'\t\tImage: {variant_image_url}')

            # TODO: Here we need to click a link while it exists. Should create a corresponding option in config.
            load_more_xpath = "//td[contains(@class, 'navigation')]/a[2][@class='navigation']"
            link_load_more = self.browser.find_elements_by_xpath(load_more_xpath)
            if len(link_load_more):
                try:
                    link_load_more[0].click()
                except WebDriverException as wd_ex:
                    logging.error(f'Selenium failed to click element {load_more_xpath} on page {url_to_scrape["url"]}. Error message: {wd_ex}')
                clicks += 1
                if clicks > 10:
                    logging.warning(f"Too many clicks on page {url_to_scrape['url']}, selector: {load_more_xpath}")
                    continue_scraping = False
            else:
                continue_scraping = False


    def get_web_element_attribute(self, selector, parent_web_element=None):
        if not parent_web_element or selector.startswith('//'):
            parent_web_element = self.browser

        result = None

        possible_attribute = selector.split('/')[-1]
        possible_selector = selector.replace(possible_attribute, '').rstrip('/')
        possible_attribute = possible_attribute.lower()
        if possible_attribute == 'text()':
            element = parent_web_element.find_elements_by_xpath(possible_selector)
            if len(element):
                result = element[0].text
        elif possible_attribute.startswith('@'):
            element = parent_web_element.find_elements_by_xpath(possible_selector)
            if len(element):
                result = element[0].get_attribute(possible_attribute.lstrip('@'))
        else:
            element = parent_web_element.find_elements_by_xpath(selector)
            if len(element):
                result = element[0].get_attribute('innerHTML')

        if result is None:
            logging.warning(f'Selector hit nothing!: {selector}, URL: {self.browser.current_url}')
        return result

    def select_image_url_where_variant_id(self, variant_id):
        for ik in self.t_product_variant_images_work.keys():
            if self.t_product_variant_images_work[ik]['variant_id'] == variant_id:
                return self.t_product_variant_images_work[ik]['url']
        return None

    def select_variants_where_product_key(self, product_key):
        variants = list()
        for vk in self.t_product_variants_work.keys():
            if self.t_product_variants_work[vk]['product_record_id'] == product_key:
                variants.append(self.t_product_variants_work[vk])
        return variants


if __name__ == "__main__":
    with open('config.json') as scraping_config_file:
        config_json = json.loads(scraping_config_file.read())

    logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
                        datefmt='%d-%m-%Y:%H:%M:%S',
                        level=logging.DEBUG)
    logging.getLogger("selenium").setLevel(logging.INFO)

    scraper = Scraper(config_json, headless=True, disable_images=False)
    scraper.scrape(get_interval=0.05)
    scraper.save_results_to_xslx('results.xlsx')