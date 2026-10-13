"""Validated decision executor shared by offline and real-LLM providers."""
import json
import re
from pathlib import Path

import refund_service as tools

ROUTES = {'ANSWER_POLICY', 'ASK_FOR_INFO', 'GET_ORDER', 'CHECK_REFUND',
          'PROCESS_REFUND', 'ESCALATE'}
INTENTS = {'policy', 'order', 'refund', 'damage', 'unknown'}
DECISION_KEYS = {'intent', 'route', 'order_id', 'tool', 'action', 'reason',
                 'escalated'}
PROPOSED_TOOLS = {'read_policy', 'get_order', 'check_refund_eligibility',
                  'process_refund'}
INTENT_ROUTES = {
    'policy': {'ANSWER_POLICY', 'ASK_FOR_INFO'},
    'order': {'GET_ORDER', 'ASK_FOR_INFO'},
    'refund': {'CHECK_REFUND', 'PROCESS_REFUND', 'ASK_FOR_INFO'},
    'damage': {'ESCALATE'},
    'unknown': {'ESCALATE', 'ASK_FOR_INFO'},
}

STATUS_LABELS = {
    'PROCESSING': ('being processed', '正在处理中'),
    'SHIPPED': ('shipped', '已发货'),
    'IN_TRANSIT': ('in transit', '运输中'),
    'DELIVERED': ('delivered', '已送达'),
    'LOST': ('marked as lost', '已被系统标记为丢失'),
    'CANCELLED': ('cancelled', '已取消'),
}


def response_language(message):
    """Use Chinese for Chinese or mixed input; otherwise use English."""
    return 'zh' if re.search(r'[\u3400-\u9fff]', message) else 'en'


def order_lookup_response(order, language):
    """Present stored order facts without leaking internal field names."""
    status = STATUS_LABELS[order['status']][language == 'zh']
    if language == 'zh':
        reply = f"订单 {order['order_id']} 当前{status}。"
        if order['status'] in {'PROCESSING', 'SHIPPED', 'IN_TRANSIT'}:
            reply += f"预计送达日期为 {order['estimated_delivery']}。"
        return reply
    reply = f"Order {order['order_id']} is currently {status}."
    if order['status'] in {'PROCESSING', 'SHIPPED', 'IN_TRANSIT'}:
        reply += f" Its estimated delivery date is {order['estimated_delivery']}."
    return reply


def policy_response(message, policy, language):
    """Answer only the policy topic present in the user's message when known."""
    text = message.lower()
    rules = policy['rules']
    if any(word in text for word in ('lost', '丢失')):
        key = 'lost_confirmed_by_system'
        replies = (
            'Under the fictional prototype policy, an order confirmed lost by the system qualifies for an automatic refund.',
            '根据当前虚构的原型政策，系统确认丢失的订单可以自动退款。',
        )
    elif any(word in text for word in ('in-transit', 'in transit', '运输', '途中')):
        key = 'in_transit'
        replies = (
            'Under the fictional prototype policy, an in-transit order cannot be automatically refunded; exceptions require human review.',
            '根据当前虚构的原型政策，运输中的订单不能自动退款；例外情况需要人工审核。',
        )
    elif any(word in text for word in ('cancelled', 'canceled', '取消')):
        key = 'cancelled_before_shipment'
        replies = (
            'Under the fictional prototype policy, an order cancelled before shipment qualifies for an automatic refund.',
            '根据当前虚构的原型政策，发货前取消的订单可以自动退款。',
        )
    elif any(word in text for word in ('damaged', 'broken', '损坏', '破损')):
        key = 'damaged_unverified'
        replies = (
            'Under the fictional prototype policy, an unverified damaged-item claim requires human review.',
            '根据当前虚构的原型政策，未经核实的商品损坏申请需要人工审核。',
        )
    else:
        lines = [
            'Cancelled before shipment: ' + rules['cancelled_before_shipment'],
            'System-confirmed lost: ' + rules['lost_confirmed_by_system'],
            'Unverified damage: ' + rules['damaged_unverified'],
            'In transit: ' + rules['in_transit'],
            'Other statuses: ' + rules['other_statuses'],
        ]
        if language == 'zh':
            lines = [
                '发货前取消：可以自动退款。',
                '系统确认丢失：可以自动退款。',
                '未经核实的损坏：需要人工审核。',
                '运输中：不能自动退款；例外情况需要人工审核。',
                '其他状态：Sprint 1 不允许自动退款。',
            ]
        heading = ('当前虚构的原型退款政策：' if language == 'zh'
                   else 'Current fictional prototype refund policy:')
        return heading + '\n' + '\n'.join(f'- {line}' for line in lines)
    # Accessing the selected key keeps the response tied to an existing policy fact.
    if key not in rules:
        raise KeyError(key)
    return replies[language == 'zh']


def missing_information_response(intent, language):
    if intent == 'refund':
        return ('请提供要退款的订单号，例如 ORD-1017。' if language == 'zh'
                else 'Please provide the order ID you want refunded, for example ORD-1017.')
    if intent == 'order':
        return ('请提供要查询的订单号，例如 ORD-1017。' if language == 'zh'
                else 'Please provide the order ID you want to check, for example ORD-1017.')
    return ('请补充问题和一个订单号，例如 ORD-1017。' if language == 'zh'
            else 'Please provide more detail and one order ID, for example ORD-1017.')


def order_ids(message):
    return set(re.findall(r'\bORD-\d+\b', message.upper()))


def mock_decision(message):
    """Small bilingual keyword fixture, not genuine language understanding."""
    text = message.lower()
    ids = order_ids(message)
    order_id = next(iter(ids)) if len(ids) == 1 else None
    if any(word in text for word in ('damaged', 'broken', '损坏', '破损')):
        intent, route = 'damage', 'ESCALATE'
    elif any(word in text for word in ('policy', 'policies', '政策', '规则')):
        intent, route = 'policy', 'ANSWER_POLICY'
    elif any(word in text for word in ('refund', '退款')):
        intent, route = 'refund', 'CHECK_REFUND' if order_id else 'ASK_FOR_INFO'
    elif ids or any(word in text for word in ('order', 'package', 'delivery', '订单', '包裹', '物流')):
        intent, route = 'order', 'GET_ORDER' if order_id else 'ASK_FOR_INFO'
    else:
        intent, route = 'unknown', 'ESCALATE'
    proposed_tools = {
        'ANSWER_POLICY': ['read_policy'],
        'GET_ORDER': ['get_order'],
        'CHECK_REFUND': ['get_order', 'check_refund_eligibility'],
    }.get(route, [])
    return dict(intent=intent, route=route, order_id=order_id,
                tool=proposed_tools, action='NONE', reason='MOCK_CLASSIFICATION',
                escalated=route == 'ESCALATE')


mock_decision.mode = 'OFFLINE_MOCK'


def validate_decision(proposal):
    """Accept only the small, explicit decision contract used by the executor."""
    if (not isinstance(proposal, dict)
            or set(proposal) != DECISION_KEYS
            or not isinstance(proposal['intent'], str)
            or proposal['intent'] not in INTENTS
            or not isinstance(proposal['route'], str)
            or proposal['route'] not in ROUTES
            or proposal['route'] not in INTENT_ROUTES[proposal['intent']]
            or (proposal['order_id'] is not None and
                not isinstance(proposal['order_id'], str))
            or not isinstance(proposal['tool'], list)
            or any(not isinstance(tool, str) or tool not in PROPOSED_TOOLS
                   for tool in proposal['tool'])
            or proposal['action'] != 'NONE'
            or not isinstance(proposal['reason'], str)
            or not isinstance(proposal['escalated'], bool)
            or proposal['escalated'] != (proposal['route'] == 'ESCALATE')):
        raise ValueError('Invalid decision')
    return proposal


def handle_message(message, decision_provider=mock_decision, confirmed_order_id=None):
    """Validate an untrusted proposal and execute a bounded tool sequence.

    Confirmation is an independent UI input, never a field supplied by the model.
    Every refund is authorized by existing deterministic tools using stored data.
    """
    result = dict(intent='unknown', route='ESCALATE', order_id=None, tool=[],
                  action='NONE', reason='', escalated=False, message='',
                  mode=getattr(decision_provider, 'mode', 'CUSTOM_PROVIDER'))

    def finish(route, reason, reply):
        result.update(route=route, reason=reason, message=reply,
                      escalated=route == 'ESCALATE')
        return result

    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        return finish('ASK_FOR_INFO', 'INVALID_MESSAGE', '请输入问题（最多 4000 字）。')
    try:
        proposal = validate_decision(decision_provider(message))
    except Exception:
        return finish('ESCALATE', 'INVALID_DECISION', '决策不可用，需要人工查看；尚未执行退款。')
    # The provider proposes all fields, but only these three classification fields
    # are consumed. Tool traces and actions are always produced by this executor.
    result['model_decision'] = proposal
    result.update({key: proposal[key] for key in ('intent', 'route', 'order_id')})
    language = response_language(message)
    ids = order_ids(message)
    oid = proposal['order_id']
    if len(ids) > 1:
        reply = ('每次请只提供一个订单号。' if language == 'zh'
                 else 'Please provide only one order ID at a time.')
        return finish('ASK_FOR_INFO', 'MULTIPLE_ORDERS', reply)
    if oid is not None and oid not in ids:
        return finish('ESCALATE', 'ORDER_ID_MISMATCH', '决策中的订单号与输入不一致。')
    # Conservative guard independent of the supplied decision provider.
    if any(word in message.lower() for word in ('damaged', 'broken', '损坏', '破损')):
        return finish('ESCALATE', 'DAMAGED_CLAIM_UNVERIFIED', '损坏声明需要人工审核。')
    route = proposal['route']
    if route == 'ESCALATE':
        return finish(route, 'HUMAN_REVIEW_REQUIRED', '需要人工查看。此原型不会实际创建人工工单。')
    if route == 'ASK_FOR_INFO':
        return finish(route, 'MISSING_INFORMATION',
                      missing_information_response(proposal['intent'], language))
    if route == 'ANSWER_POLICY':
        policy = json.loads(Path(__file__).with_name('policies.json').read_text())
        result['tool'].append('read_policy')
        return finish(route, 'POLICY_SOURCE', policy_response(message, policy, language))
    if oid is None:
        return finish('ASK_FOR_INFO', 'MISSING_ORDER_ID', '请提供一个订单号，例如 ORD-1017。')
    result['tool'].append('get_order')
    order = tools.get_order(oid)
    if not order:
        return finish('ASK_FOR_INFO', 'ORDER_NOT_FOUND', '找不到订单，请检查订单号。')
    result['order'] = order
    if route == 'GET_ORDER':
        return finish(route, 'ORDER_FOUND', order_lookup_response(order, language))
    result['tool'].append('check_refund_eligibility')
    eligibility = tools.check_refund_eligibility(order)
    result['eligibility'] = eligibility
    if eligibility['decision'] != 'ELIGIBLE':
        return finish('ESCALATE' if eligibility['decision'] == 'NEEDS_REVIEW' else 'CHECK_REFUND',
                      eligibility['reason'], eligibility['message'])
    if confirmed_order_id != oid:
        result['confirmation_order_id'] = oid
        return finish('CHECK_REFUND', 'CONFIRMATION_REQUIRED',
                      '符合模拟退款规则。如需执行，请勾选确认并填写同一个订单号后重新提交。')
    result['tool'].append('process_refund')
    refund = tools.process_refund(oid)
    result['refund'] = refund
    result['action'] = 'SIMULATED_REFUND_COMPLETED' if refund['success'] else 'NONE'
    return finish('PROCESS_REFUND' if refund['success'] else
                  ('ESCALATE' if refund['decision'] == 'NEEDS_REVIEW' else 'CHECK_REFUND'),
                  refund['reason'], refund['message'])
