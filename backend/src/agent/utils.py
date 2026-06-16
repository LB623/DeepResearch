from typing import Any, Dict, List
from langchain_core.messages import AnyMessage, AIMessage, HumanMessage
from loguru import logger


def get_research_topic(messages: List[AnyMessage], ignore_contexts: List[str]=None) -> str:
    """
    从messages中获取research主题。
    """
    # check if request has a history and combine the messages into a single string
    if not ignore_contexts:
        ignore_contexts = []
    if len(messages) == 1:
        research_topic = messages[-1].content
    else:
        research_topic = ""
        for message in messages:
            if isinstance(message, HumanMessage):
                research_topic += f"User: {message.content}\n"
            elif isinstance(message, AIMessage) and message.content not in ignore_contexts:
                research_topic += f"Assistant: {message.content}\n"
    return research_topic

def get_last_user_response(messages: List[AnyMessage]) -> str:
    user_messages = [msg for msg in messages if isinstance(msg, HumanMessage)]
    if user_messages:
        return f"User: {user_messages[-1].content}\n"
    return ""

def resolve_urls(urls_to_resolve: List[Any], id: int) -> Dict[str, str]:
    """
    创建一个ai搜索url(可能非常长)到一个短url的映射，每个URL有一个唯一的id.
    每个原始URL获得一致的缩写形式，同时保持唯一性.
    """
    prefix = f"https://search.com/id/"
    
    # 检查urls_to_resolve是否为None或空列表
    if urls_to_resolve is None:
        logger.warning(f"urls_to_resolve为None，返回空映射")
        return {}
    
    if not isinstance(urls_to_resolve, list):
        logger.warning(f"urls_to_resolve不是列表类型: {type(urls_to_resolve)}，返回空映射")
        return {}
    
    if len(urls_to_resolve) == 0:
        logger.warning(f"urls_to_resolve为空列表，返回空映射")
        return {}
    
    urls = [site["url"] for site in urls_to_resolve if isinstance(site, dict) and "url" in site]

    # Create a dictionary that maps each unique URL to its first occurrence index
    resolved_map = {}
    for idx, url in enumerate(urls):
        if url not in resolved_map:
            resolved_map[url] = f"{prefix}{id}-{idx}"

    return resolved_map
