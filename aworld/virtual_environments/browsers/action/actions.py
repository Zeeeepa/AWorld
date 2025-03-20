# coding: utf-8
# Copyright (c) 2025 inclusionAI.
import traceback

import asyncio
import time
from typing import Tuple, Any

from langchain_core.prompts import PromptTemplate

from aworld.core.action import BrowserAction
from aworld.core.action_factory import ActionFactory
from aworld.core.common import ActionModel, ActionResult, Observation, Tools
from aworld.core.dom import DOMElementNode
from aworld.logs.util import logger
from aworld.virtual_environments.browsers.action.utils import DomUtil
from aworld.virtual_environments.action import ExecutableAction


def get_page(**kwargs):
    tool = kwargs.get("tool")
    if tool is None:
        page = kwargs.get('page')
    else:
        page = tool.page
    return page


def get_browser(**kwargs):
    tool = kwargs.get("tool")
    if tool is None:
        page = kwargs.get('browser')
    else:
        page = tool.context
    return page


@ActionFactory.register(name=BrowserAction.GO_TO_URL.value.name,
                        desc=BrowserAction.GO_TO_URL.value.desc,
                        tool_name=Tools.BROWSER.value)
class GotoUrl(ExecutableAction):
    def act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.GO_TO_URL.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.GO_TO_URL.name} page is none")
            return ActionResult(content="no page", keep=True), page

        params = action.params
        url = params.get("url")
        page.goto(url)
        page.wait_for_load_state()
        msg = f'Navigated to {url}'
        logger.info(msg)
        return ActionResult(content=msg, keep=True), page

    async def async_act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.GO_TO_URL.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.GO_TO_URL.name} page is none")
            return ActionResult(content="no page", keep=True), page

        url = action.params.get("url")
        if not url:
            logger.warning("empty url, go to nothing.")
            return ActionResult(content="empty url", keep=True), page

        await page.goto(url)
        await page.wait_for_load_state()
        msg = f'Navigated to {url}'
        logger.info(msg)
        return ActionResult(content=msg, keep=True), page


@ActionFactory.register(name=BrowserAction.INPUT_TEXT.value.name,
                        desc=BrowserAction.INPUT_TEXT.value.desc,
                        tool_name=Tools.BROWSER.value)
class InputText(ExecutableAction):
    def act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.INPUT_TEXT.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.INPUT_TEXT.name} page is none")
            return ActionResult(content="input text no page", keep=True), page

        params = action.params
        index = params.get("index")
        input = params.get("text", "")

        ob: Observation = kwargs.get("observation")
        if not ob or index not in ob.dom_tree.element_map:
            raise RuntimeError(f'Element index {index} does not exist')
        if not input:
            raise ValueError(f'No input to the page')

        element_node = ob.dom_tree.element_map[index]
        self.input_to_element(input, page, element_node)
        msg = f'Input {input} into index {index}'
        logger.info(f"action {msg}")
        logger.debug(f'Element xpath: {element_node.xpath}')
        return ActionResult(content=msg, keep=True), page

    async def async_act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.INPUT_TEXT.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.INPUT_TEXT.name} page is none")
            return ActionResult(content="input text no page", keep=True), page

        params = action.params
        index = params.get("index")
        input = params.get("text", "")

        ob: Observation = kwargs.get("observation")
        if not ob or index not in ob.dom_tree.element_map:
            raise RuntimeError(f'Element index {index} does not exist')
        if not input:
            raise ValueError(f'No input to the page')

        element_node = ob.dom_tree.element_map[index]
        await self.async_input_to_element(input, page, element_node)
        msg = f'Input {input} into index {index}'
        logger.info(f"action {msg}")
        logger.debug(f'Element xpath: {element_node.xpath}')
        return ActionResult(content=msg, keep=True), page

    def input_to_element(self, input: str, page, element_node: DOMElementNode):
        try:
            # Highlight before typing
            # if element_node.highlight_index is not None:
            # 	await self._update_state(focus_element=element_node.highlight_index)

            element_handle = DomUtil.get_locate_element(page, element_node)

            if element_handle is None:
                raise RuntimeError(f'Element: {repr(element_node)} not found')

            # Ensure element is ready for input
            try:
                element_handle.wait_for_element_state('stable', timeout=1000)
                element_handle.scroll_into_view_if_needed(timeout=1000)
            except Exception:
                pass

            # Get element properties to determine input method
            is_contenteditable = element_handle.get_property('isContentEditable')

            # Different handling for contenteditable vs input fields
            if is_contenteditable.json_value():
                element_handle.evaluate('el => el.textContent = ""')
                element_handle.type(input, delay=5)
            else:
                element_handle.fill(input)

        except Exception as e:
            logger.warning(f'Failed to input text into element: {repr(element_node)}. Error: {str(e)}')
            raise RuntimeError(f'Failed to input text into index {element_node.highlight_index}')

    async def async_input_to_element(self, input: str, page, element_node: DOMElementNode):
        try:
            element_handle = await DomUtil.async_get_locate_element(page, element_node)

            if element_handle is None:
                raise RuntimeError(f'Element: {repr(element_node)} not found')

            # Ensure element is ready for input
            try:
                await element_handle.wait_for_element_state('stable', timeout=1000)
                await element_handle.scroll_into_view_if_needed(timeout=1000)
            except Exception:
                pass

            # Get element properties to determine input method
            is_contenteditable = await element_handle.get_property('isContentEditable')

            # Different handling for contenteditable vs input fields
            if await is_contenteditable.json_value():
                await element_handle.evaluate('el => el.textContent = ""')
                await element_handle.type(input, delay=5)
            else:
                await element_handle.fill(input)
        except Exception as e:
            logger.warning(f'Failed to input text into element: {repr(element_node)}. Error: {str(e)}')
            raise RuntimeError(f'Failed to input text into index {element_node.highlight_index}')


@ActionFactory.register(name=BrowserAction.CLICK_ELEMENT.value.name,
                        desc=BrowserAction.CLICK_ELEMENT.value.desc,
                        tool_name=Tools.BROWSER.value)
class ClickElement(ExecutableAction):
    def act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        from playwright.sync_api import Page, BrowserContext

        logger.info(f"exec {BrowserAction.CLICK_ELEMENT.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.CLICK_ELEMENT.name} page is none")
            return ActionResult(content="input text no page", keep=True), page

        browser: BrowserContext = get_browser(**kwargs)
        if browser is None:
            logger.warning(f"{BrowserAction.CLICK_ELEMENT.name} browser context is none")
            return ActionResult(content="none browser context", keep=True), page

        index = action.params.get("index")
        ob: Observation = kwargs.get("observation")
        if not ob or index not in ob.dom_tree.element_map:
            raise RuntimeError(f'Element index {index} does not exist')
        if not input:
            raise ValueError(f'No input to the page')
        element_node = ob.dom_tree.element_map[index]

        try:
            pages = len(browser.pages)
            msg = f'Clicked button with index {index}: {element_node.get_all_text_till_next_clickable_element(max_depth=2)}'
            logger.info(msg)

            DomUtil.click_element(page, element_node, browser=browser)
            logger.debug(f'Element xpath: {element_node.xpath}')
            if len(browser.pages) > pages:
                new_tab_msg = 'Open the new tab'
                msg += f' - {new_tab_msg}'
                logger.info(new_tab_msg)
                page = browser.pages[-1]
                page.bring_to_front()
                page.wait_for_load_state(timeout=60000)
            return ActionResult(content=msg, keep=True), page
        except Exception as e:
            logger.warning(f'Element not clickable with index {index} - most likely the page changed')
            return ActionResult(error=str(e)), page

    async def async_act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.CLICK_ELEMENT.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warn(f"{BrowserAction.CLICK_ELEMENT.name} page is none")
            return ActionResult(content="input text no page", keep=True), page

        browser = get_browser(**kwargs)
        if browser is None:
            logger.warning(f"{BrowserAction.CLICK_ELEMENT.name} browser context is none")
            return ActionResult(content="none browser context", keep=True), page

        index = action.params.get("index")
        ob: Observation = kwargs.get("observation")
        if not ob or index not in ob.dom_tree.element_map:
            raise RuntimeError(f'Element index {index} does not exist')
        if not input:
            raise ValueError(f'No input to the page')
        element_node = ob.dom_tree.element_map[index]
        pages = len(browser.pages)

        try:
            await DomUtil.async_click_element(page, element_node, browser=browser)
            msg = f'Clicked button with index {index}: {element_node.get_all_text_till_next_clickable_element(max_depth=2)}'

            logger.info(msg)
            logger.debug(f'Element xpath: {element_node.xpath}')
            if len(browser.pages) > pages:
                new_tab_msg = 'Open the new tab'
                msg += f' - {new_tab_msg}'
                logger.info(new_tab_msg)
                page = browser.pages[-1]
                await page.bring_to_front()
                await page.wait_for_load_state(timeout=60000)
            return ActionResult(content=msg, keep=True), page
        except Exception as e:
            logger.warning(f'Element not clickable with index {index} - most likely the page changed')
            return ActionResult(error=str(e)), page


SEARCH_ENGINE = {"": "https://www.google.com/search?udm=14&q=",
                 "google": "https://www.google.com/search?udm=14&q="}


@ActionFactory.register(name=BrowserAction.SEARCH.value.name,
                        desc=BrowserAction.SEARCH.value.desc,
                        tool_name=Tools.BROWSER.value)
class Search(ExecutableAction):
    def act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.SEARCH.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.SEARCH.name} page is none")
            return ActionResult(content="search no page", keep=True), page

        params = action.params if action.params else {}
        engine = params.get("engine", "")
        url = SEARCH_ENGINE.get(engine)
        query = params.get("query")
        page.goto(f'{url}{query}')
        page.wait_for_load_state()
        msg = f'Searched for "{query}" in {url}'
        logger.info(msg)
        return ActionResult(content=msg, keep=True), page

    async def async_act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.SEARCH.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.SEARCH.name} page is none")
            return ActionResult(content="search no page", keep=True), page

        params = action.params if action.params else {}
        engine = params.get("engine", "")
        url = SEARCH_ENGINE.get(engine)
        query = params.get("query")
        await page.goto(f'{url}{query}')
        await page.wait_for_load_state()
        msg = f'Searched for "{query}" in {url}'
        logger.info(msg)
        return ActionResult(content=msg, keep=True), page


@ActionFactory.register(name=BrowserAction.SEARCH_GOOGLE.value.name,
                        desc=BrowserAction.SEARCH_GOOGLE.value.desc,
                        tool_name=Tools.BROWSER.value)
class SearchGoogle(ExecutableAction):
    def act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.SEARCH_GOOGLE.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.SEARCH_GOOGLE.name} page is none")
            return ActionResult(content="search no page", keep=True), page

        query = action.params.get("query")
        page.goto(f'{SEARCH_ENGINE.get("")}{query}')
        page.wait_for_load_state()
        msg = f'Searched for "{query}" in Google'
        logger.info(msg)
        return ActionResult(content=msg, keep=True), page

    async def async_act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.SEARCH_GOOGLE.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.SEARCH_GOOGLE.name} page is none")
            return ActionResult(content="search no page", keep=True), page

        query = action.params.get("query")
        await page.goto(f'{SEARCH_ENGINE.get("")}{query}')
        await page.wait_for_load_state()
        msg = f'Searched for "{query}" in Google'
        logger.info(msg)
        return ActionResult(content=msg, keep=True), page


@ActionFactory.register(name=BrowserAction.GO_BACK.value.name,
                        desc=BrowserAction.GO_BACK.value.desc,
                        tool_name=Tools.BROWSER.value)
class GoBack(ExecutableAction):
    def act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.GO_BACK.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.GO_BACK.name} page is none")
            return ActionResult(content="search no page", keep=True), page

        page.go_back()
        msg = 'Navigated back'
        logger.info(msg)
        return ActionResult(content=msg, keep=True), page

    async def async_act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.GO_BACK.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.GO_BACK.name} page is none")
            return ActionResult(content="search no page", keep=True), page

        await page.go_back()
        msg = 'Navigated back'
        logger.info(msg)
        return ActionResult(content=msg, keep=True), page


@ActionFactory.register(name=BrowserAction.EXTRACT_CONTENT.value.name,
                        desc=BrowserAction.EXTRACT_CONTENT.value.desc,
                        tool_name=Tools.BROWSER.value)
class ExtractContent(ExecutableAction):
    def act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        import markdownify

        logger.info(f"exec {BrowserAction.EXTRACT_CONTENT.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.EXTRACT_CONTENT.name} page is none")
            return ActionResult(content="extract content no page", keep=True), page

        goal = action.params.get("goal")
        llm = kwargs.get("llm")
        content = markdownify.markdownify(page.content())

        prompt = 'Your task is to extract the content of the page. You will be given a page and a goal and you should extract all relevant information around this goal from the page. If the goal is vague, summarize the page. Respond in json format. Extraction goal: {goal}, Page: {page}'
        template = PromptTemplate(input_variables=['goal', 'page'], template=prompt)
        try:
            output = llm.invoke(template.format(goal=goal, page=content))
            msg = f'Extracted from page\n: {output.content}\n'
            logger.info(msg)
            return ActionResult(content=msg, keep=True), page
        except Exception as e:
            logger.debug(f'Error extracting content: {e}')
            msg = f'Extracted from page\n: {content}\n'
            logger.info(msg)
            return ActionResult(content=msg), page

    async def async_act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        import markdownify

        logger.info(f"exec {BrowserAction.EXTRACT_CONTENT.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.EXTRACT_CONTENT.name} page is none")
            return ActionResult(content="extract content no page", keep=True), page

        goal = action.params.get("goal")
        llm = kwargs.get("llm")
        content = markdownify.markdownify(page.content())

        prompt = 'Your task is to extract the content of the page. You will be given a page and a goal and you should extract all relevant information around this goal from the page. If the goal is vague, summarize the page. Respond in json format. Extraction goal: {goal}, Page: {page}'
        template = PromptTemplate(input_variables=['goal', 'page'], template=prompt)
        try:
            output = llm.invoke(template.format(goal=goal, page=content))
            msg = f'Extracted from page\n: {output.content}\n'
            logger.info(msg)
            return ActionResult(content=msg, keep=True), page
        except Exception as e:
            logger.debug(f'Error extracting content: {e}')
            msg = f'Extracted from page\n: {content}\n'
            logger.info(msg)
            return ActionResult(content=msg), page


@ActionFactory.register(name=BrowserAction.SCROLL_DOWN.value.name,
                        desc=BrowserAction.SCROLL_DOWN.value.desc,
                        tool_name=Tools.BROWSER.value)
class ScrollDown(ExecutableAction):
    def act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.SCROLL_DOWN.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.SCROLL_DOWN.name} page is none")
            return ActionResult(content="scroll no page", keep=True), page

        amount = action.params.get("amount")
        if amount:
            page.evaluate('window.scrollBy(0, window.innerHeight);')
        else:
            page.evaluate(f'window.scrollBy(0, {amount});')

        amount = f'{amount} pixels' if amount else 'one page'
        msg = f'Scrolled down the page by {amount}'
        logger.info(msg)
        return ActionResult(content=msg, keep=True), page

    async def async_act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.SCROLL_DOWN.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.SCROLL_DOWN.name} page is none")
            return ActionResult(content="scroll no page", keep=True), page

        amount = action.params.get("amount")
        if amount:
            await page.evaluate('window.scrollBy(0, window.innerHeight);')
        else:
            await page.evaluate(f'window.scrollBy(0, {amount});')

        amount = f'{amount} pixels' if amount else 'one page'
        msg = f'Scrolled down the page by {amount}'
        logger.info(msg)
        return ActionResult(content=msg, keep=True), page


@ActionFactory.register(name=BrowserAction.SCROLL_UP.value.name,
                        desc=BrowserAction.SCROLL_UP.value.desc,
                        tool_name=Tools.BROWSER.value)
class ScrollUp(ExecutableAction):
    def act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.SCROLL_UP.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.SCROLL_UP.name} page is none")
            return ActionResult(content="scroll no page", keep=True), page

        amount = action.params.get("amount")
        if amount:
            page.evaluate('window.scrollBy(0, -window.innerHeight);')
        else:
            page.evaluate(f'window.scrollBy(0, -{amount});')

        amount = f'{amount} pixels' if amount else 'one page'
        msg = f'Scrolled down the page by {amount}'
        logger.info(msg)
        return ActionResult(content=msg, keep=True), page

    async def async_act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.SCROLL_UP.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.SCROLL_UP.name} page is none")
            return ActionResult(content="scroll no page", keep=True), page

        amount = action.params.get("amount")
        if amount:
            await page.evaluate('window.scrollBy(0, -window.innerHeight);')
        else:
            await page.evaluate(f'window.scrollBy(0, -{amount});')

        amount = f'{amount} pixels' if amount else 'one page'
        msg = f'Scrolled down the page by {amount}'
        logger.info(msg)
        return ActionResult(content=msg, keep=True), page


@ActionFactory.register(name=BrowserAction.WAIT.value.name,
                        desc=BrowserAction.WAIT.value.desc,
                        tool_name=Tools.BROWSER.value)
class Wait(ExecutableAction):
    def act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        seconds = action.params.get("seconds")
        msg = f'Waiting for {seconds} seconds'
        logger.info(msg)
        time.sleep(seconds)
        return ActionResult(content=msg, keep=True), kwargs.get('page')

    async def async_act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        seconds = action.params.get("seconds")
        msg = f'Waiting for {seconds} seconds'
        logger.info(msg)
        await asyncio.sleep(seconds)
        return ActionResult(content=msg, keep=True), kwargs.get('page')


@ActionFactory.register(name=BrowserAction.SWITCH_TAB.value.name,
                        desc=BrowserAction.SWITCH_TAB.value.desc,
                        tool_name=Tools.BROWSER.value)
class SwitchTab(ExecutableAction):
    def act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.SWITCH_TAB.value.name} action")
        browser = get_browser(**kwargs)
        if browser is None:
            logger.warning(f"{BrowserAction.SWITCH_TAB.name} browser context is none")
            return ActionResult(content="switch tab no browser context", keep=True), get_page(**kwargs)

        page_id = action.params.get("page_id")
        pages = browser.pages

        if page_id >= len(pages):
            raise RuntimeError(f'No tab found with page_id: {page_id}')

        page = pages[page_id]
        page.bring_to_front()
        page.wait_for_load_state()
        msg = f'Switched to tab {page_id}'
        logger.info(msg)
        return ActionResult(content=msg, keep=True), page

    async def async_act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.SWITCH_TAB.value.name} action")
        browser = get_browser(**kwargs)
        if browser is None:
            logger.warning(f"{BrowserAction.SWITCH_TAB.name} browser context is none")
            return ActionResult(content="switch tab no browser context", keep=True), get_page(**kwargs)

        page_id = action.params.get("page_id")
        pages = browser.pages

        if page_id >= len(pages):
            raise RuntimeError(f'No tab found with page_id: {page_id}')

        page = pages[page_id]
        await page.bring_to_front()
        await page.wait_for_load_state()
        msg = f'Switched to tab {page_id}'
        logger.info(msg)
        return ActionResult(content=msg, keep=True), page


@ActionFactory.register(name=BrowserAction.SEND_KEYS.value.name,
                        desc=BrowserAction.SEND_KEYS.value.desc,
                        tool_name=Tools.BROWSER.value)
class SendKeys(ExecutableAction):
    def act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.SEND_KEYS.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.SEND_KEYS.name} page is none")
            return ActionResult(content="scroll no page", keep=True), page

        keys = action.params.get("keys")
        if not keys:
            return ActionResult(success=False, content="no keys", keep=True), page

        try:
            page.keyboard.press(keys)
        except Exception as e:
            logger.warning(f"{keys} press fail. \n{traceback.format_exc()}")
            raise e
        return ActionResult(content=f"Sent keys: {keys}", keep=True), page

    async def async_act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.SEND_KEYS.value.name} action")
        page = get_page(**kwargs)
        if page is None:
            logger.warning(f"{BrowserAction.SEND_KEYS.name} page is none")
            return ActionResult(content="scroll no page", keep=True), page

        keys = action.params.get("keys")
        if not keys:
            return ActionResult(success=False, content="no keys", keep=True), page

        try:
            await page.keyboard.press(keys)
        except Exception as e:
            logger.warning(f"{keys} press fail. \n{traceback.format_exc()}")
            raise e

        return ActionResult(content=f"Sent keys: {keys}", keep=True), page


@ActionFactory.register(name=BrowserAction.WRITE_TO_FILE.value.name,
                        desc=BrowserAction.WRITE_TO_FILE.value.desc,
                        tool_name=Tools.BROWSER.value)
class WriteToFile(ExecutableAction):
    def act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        file_path = action.params.get("file_path", "tmp_result.md")
        content = action.params.get("content", "")
        mode = action.params.get("mode", "a")  # Default to append mode
        try:
            with open(file_path, mode, encoding='utf-8') as f:
                f.write(content + '\n')

            msg = f'Successfully wrote content to {file_path}'
            logger.info(msg)
            return ActionResult(content=msg, keep=True), kwargs.get('page')
        except Exception as e:
            error_msg = f'Failed to write to file {file_path}: {str(e)}'
            logger.error(error_msg)
            return ActionResult(content=error_msg, keep=True, error=error_msg), kwargs.get('page')

    async def async_act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        # For file operations, we don't need to make this asynchronous
        return self.act(action, **kwargs)


@ActionFactory.register(name=BrowserAction.DONE.value.name,
                        desc=BrowserAction.DONE.value.desc,
                        tool_name=Tools.BROWSER.value)
class Done(ExecutableAction):
    def act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.DONE.value.name} action")
        return ActionResult(is_done=True, success=True, content="done", keep=True), get_page(**kwargs)

    async def async_act(self, action: ActionModel, **kwargs) -> Tuple[ActionResult, Any]:
        logger.info(f"exec {BrowserAction.DONE.value.name} action")
        return ActionResult(is_done=True, success=True, content="done", keep=True), get_page(**kwargs)
