import json
import logging
import re
from datetime import datetime
from os.path import basename
from time import sleep
from urllib.parse import urljoin, urlparse

import htmlmin
import os

import requests
import xlsxwriter as xlsxwriter
from bs4 import BeautifulSoup
from selenium.common.exceptions import WebDriverException

from requests_lxml_browser import RequestsLxmlBrowser
from selenium_chrome_browser import SeleniumChromeBrowser


def is_none_or_empty(string: str) -> bool:
    return bool(string is None or not (string.strip()))


def prettify_string(string: str) -> str:
    if is_none_or_empty(string):
        return string

    rez = string.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    rez = rez.replace('™', '').replace('®', '').replace('—', '-')
    return rez


def prettify_description(html_code: str) -> str:
    if not html_code:
        return ''

    soup = BeautifulSoup(html_code, "html.parser")
    # Removing all attributes
    for e in soup.find_all(True):
        e.attrs = {}

    # Removing unwanted tags but saving their content
    invalid_tags = ['strong', 'a', 'style']
    for tag in invalid_tags:
        for match in soup.findAll(tag):
            match.replaceWithChildren()

    # Removing unwanted tags with their content
    invalid_tags = ['script', 'img']
    for tag in invalid_tags:
        for match in soup.findAll(tag):
            match.replaceWith('')

    # Removing empty tags
    for tag in soup.find_all():
        if len(tag.text) == 0:
            tag.extract()

    rez = soup.prettify()
    rez = prettify_string(htmlmin.minify(rez, remove_comments=True, remove_empty_space=True))
    return rez


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

    def __init__(self, config: dict):

        self.config = config
        self.config['config_links']['links']['xpaths'] = [xpath.replace('/@href', '') for xpath in
                                                          self.config['config_links']['links']['xpaths']]
        self.config['config_links']['products']['xpaths'] = [xpath.replace('/@href', '') for xpath in
                                                             self.config['config_links']['products']['xpaths']]

        self.download_product_images = self.config.get('scraper', {}).get('download_product_images', True)
        if self.download_product_images:
            images_folder_name = self.config.get('website_name') or "Images"
            i = 1
            while os.path.exists(images_folder_name):
                images_folder_name = f"{self.config.get('website_name') or 'Images'}_{i}"
                i += 1
            os.mkdir(images_folder_name)
            self.product_images_folder = images_folder_name

        browser = self.config.get('scraper', {}).get('browser', 'lxml').lower()
        if browser == 'chrome':
            logging.info('Using Selenium WebDriver with Chrome browser')
            self.browser = SeleniumChromeBrowser(
                headless=self.config.get('scraper', {}).get('headless', False),
                disable_images=self.config.get('scraper', {}).get('disable_images',
                                                                  False),
                width=self.config.get('scraper', {}).get('width', 1920),
                height=self.config.get('scraper', {}).get('height', 1080),
                implicitly_wait=self.config.get('scraper', {}).get('headless', 1),
            )
        else:
            logging.info('Using Selenium WebDriver with Chrome browser')
            self.browser = RequestsLxmlBrowser(
                no_session=self.config.get('scraper', {}).get('download_product_images', True)
            )

    def scrape(self, get_interval=1.00):
        self.put_initial_url(self.UrlTypes.CATALOGUE)

        url_to_scrape = self.get_next_url_to_scrape()
        while url_to_scrape:
            try:
                self.scrape_url(url_to_scrape)
            except Exception as ex:
                logging.error(f"Error scraping url {url_to_scrape}: {ex}")
                raise ex

            url_to_scrape = self.get_next_url_to_scrape()
            sleep(get_interval)

    def save_results_to_xslx(self, report_file_name: str):
        # Create a workbook and add a worksheet.
        workbook_name = self.config.get('website_name') or "Scraping Results"
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

        additional_fields = [s for s in self.config['config_products'].get('additional_selectors', [])]
        columns = 'IJKLMNOPQRSTUVWXYZ'
        ind = 0
        for s in additional_fields:
            worksheet.write(f'{columns[ind]}1', s, bold_format)
            ind += 1

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
                ind = 8
                for s in additional_fields:
                    v = [v for v in variant['additional'] if s in v.keys()]
                    worksheet.write(row, ind, v[0][s])
                    ind += 1
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
        else:
            # logging.debug(f"Doubled link: {url}")
            pass

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

    def insert_t_product_variants_work(self, variant_sku, variant_additional, product_record_id):
        if (variant_sku, product_record_id) not in self.t_product_variants_work_pk:
            self.t_product_variants_work_pk.add((variant_sku, product_record_id))
            record_id = len(self.t_product_variants_work)
            self.t_product_variants_work[record_id] = {'sku': variant_sku,
                                                       'additional': variant_additional,
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
            # self.extract_links(url_to_scrape) # TODO: Remove it!

        self.t_links_work[url_to_scrape['record_id']]['retrieved'] = datetime.now()

    def extract_links(self, url_to_scrape):
        self.browser.get(url_to_scrape['url'])

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
                catalogue_url = urljoin(url_to_scrape['url'], self.browser.get_element_attribute(a_element, 'href'))
                if len(catalogue_url_regex_filters) and not (
                        any(regex.match(catalogue_url) for regex in catalogue_url_regex_filters)):
                    continue
                extracted_links.add((catalogue_url, self.UrlTypes.CATALOGUE))

        for product_xpath in self.config['config_links']['products']['xpaths']:
            for a_element in self.browser.find_elements_by_xpath(product_xpath):
                product_url = urljoin(url_to_scrape['url'],
                                      self.browser.get_element_attribute(a_element, 'href'))

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
        product_name = prettify_string(
            self.get_web_element_attribute(self.config['config_products']['product_selectors']['name']['sel'])
        )
        product_description = prettify_description(
            self.get_web_element_attribute(self.config['config_products']['product_selectors']['description']['sel'])
        )
        product_category1 = self.get_web_element_attribute(
            self.config['config_products']['product_selectors']['category1']['sel'])
        product_category2 = self.get_web_element_attribute(
            self.config['config_products']['product_selectors']['category2']['sel'], no_warning=True)
        product_category3 = self.get_web_element_attribute(
            self.config['config_products']['product_selectors']['category3']['sel'], no_warning=True)

        # Validating products data
        if not product_name:
            logging.warning(
                f"Unable to extract product name! This product will be skipped. URL: {url_to_scrape['url']}, selector: {self.config['config_products']['product_selectors']['name']['sel']}")
            return
        if is_none_or_empty(product_description):
            logging.warning(
                f"Product '{product_name}' has no description! URL: {url_to_scrape['url']}, selector: {self.config['config_products']['product_selectors']['description']['sel']}")
        if is_none_or_empty(product_category1) and is_none_or_empty(product_category2) and is_none_or_empty(
                product_category3) and not (
                is_none_or_empty(self.config['config_products']['product_selectors']['category1']['sel'])):
            logging.warning(f"Product '{product_name}' has no categories! URL: {url_to_scrape['url']}")

        new_product_record_id = self.insert_t_products_work(product_name, product_description, product_category1,
                                                            product_category2, product_category3, url_to_scrape['url'])
        logging.debug(f'Extracted product: {product_name}')

        # Getting a list of variants for the product
        product_variants = self.browser.find_elements_by_xpath(
            self.config['config_products']['variant_settings']['sel'])

        if not len(product_variants):
            logging.warning(
                f"Product '{product_name}' has no variants! URL: {url_to_scrape['url']}, selector: {self.config['config_products']['variant_settings']['sel']}")
            return

        variant_index = 0
        for variant in product_variants:
            variant_sku = self.get_web_element_attribute(
                self.config['config_products']['variant_settings']['product_code'],
                variant)

            variant_additional = list()
            for additional_selector_name in self.config['config_products'].get('additional_selectors', []):
                additional_selector = self.config['config_products']['additional_selectors'][
                    additional_selector_name]
                if str(additional_selector['index']).lower() == 'variant':
                    selector_index = variant_index
                else:
                    selector_index = int(additional_selector['index']) or 0  # TODO: Implement

                variant_additional.append({additional_selector_name: self.get_web_element_attribute(
                    additional_selector['sel'],
                    variant,
                    selector_index,
                    no_warning=True)})

            if is_none_or_empty(variant_sku):
                logging.warning(
                    f"Variant of product '{product_name}' has no SKU! URL: {url_to_scrape['url']}, selector: {self.config['config_products']['variant_settings']['sel']} + {self.config['config_products']['variant_settings']['product_code']}")
                continue

            new_product_variant_id = self.insert_t_product_variants_work(variant_sku, variant_additional,
                                                                         new_product_record_id)
            logging.debug(f'\tVariant: {variant_sku}')

            if new_product_variant_id is not None:
                variant_image_url = self.get_web_element_attribute(
                    self.config['config_products']['variant_settings'].get('image', self.config['config_products'][
                        'product_selectors']['image_file_name_1']['sel']),
                    variant)

                if is_none_or_empty(variant_image_url):
                    logging.warning(
                        f"Variant of product '{product_name}' has no image! URL: {url_to_scrape['url']}, selector: {self.config['config_products']['variant_settings']['sel']} + {self.config['config_products']['product_selectors']['image_file_name_1']['sel']}")
                elif self.download_product_images:
                    variant_image_url = self.download_product_image(variant_image_url)

                self.insert_t_product_variant_images_work(variant_image_url, new_product_variant_id)
                logging.debug(f'\t\tImage: {variant_image_url}')

            variant_index += 1

    def get_web_element_attribute(self, selector, parent_web_element=None, element_index=0, no_warning=False):
        if is_none_or_empty(selector):
            return None

        result = None

        selectors = selector.split("|")
        for selector in selectors:
            if selector == selectors[0] and selector.startswith('('):
                selector = selector[1:]
            if selector == selectors[-1] and not selector.endswith('()') and selector.endswith(')'):
                selector = selector[:-1]

            selector = selector.replace("\'", '"')

            if not parent_web_element or selector.startswith('//'):
                parent_web_element = self.browser.get_current_page_as_element()

            possible_attribute = selector.split('/')[-1]
            possible_selector = selector.replace(possible_attribute, '').rstrip('/')
            possible_attribute = possible_attribute.lower()
            if possible_attribute == 'text()':
                element = self.browser.find_elements_by_xpath(possible_selector, parent_web_element)
                if len(element):
                    result = element[element_index].text
                    ind = 1
                    while is_none_or_empty(result) and ind < len(element):
                        result = element[ind].text
                        # TODO: add warning
            elif possible_attribute.startswith('@'):
                element = self.browser.find_elements_by_xpath(possible_selector, parent_web_element)
                if len(element):
                    result = self.browser.get_element_attribute(element[element_index], possible_attribute.lstrip('@'))
            else:
                element = self.browser.find_elements_by_xpath(selector, parent_web_element)
                if len(element):
                    result = self.browser.get_element_attribute(element[element_index], 'innerHTML')

            if result is not None:
                break

        if result is None:
            if not no_warning:
                logging.warning(f'Selector hit nothing!: {selector}, URL: {self.browser.get_current_url()}')
            return result

        return result.strip()

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

    def download_product_image(self, image_url):
        filename = basename(image_url)
        path_to_check = os.path.join(self.product_images_folder, filename)
        target_filename = path_to_check
        i = 1
        while os.path.exists(target_filename):
            target_filename = f'{path_to_check.rsplit(".", 1)[0]}_{i}.{path_to_check.rsplit(".", 1)[1]}'
            i += 1

        try:
            r = requests.get(image_url, stream=True)
            if r.status_code != 200:
                logging.error(f"Error {r.status_code} downloading image {image_url}")
                return image_url

            with open(target_filename, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)

        except Exception as ex:
            logging.error(f"Error {ex} downloading image {image_url}")
            return image_url

        return basename(target_filename)


if __name__ == "__main__":
    with open('config.json') as scraping_config_file:
        config_json = json.loads(scraping_config_file.read())

    logging.basicConfig(format='%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
                        datefmt='%d-%m-%Y:%H:%M:%S',
                        level=logging.DEBUG)
    logging.getLogger("selenium").setLevel(logging.INFO)

    scraper = Scraper(config_json)
    scraper.scrape(get_interval=0.05)
    scraper.save_results_to_xslx('results.xlsx')
