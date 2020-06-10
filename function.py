# -*- coding: utf-8 -*-
#!/usr/bin/env python

# 导包
import datetime
from apps.web.device.models import Device, DriverCode, Group
from apps.web.dealer.models import Dealer, Merchant
from apps.web.agent.models import Agent
from apps.web.user.models import Card, MyUser, ConsumeRecord, RechargeRecord
from apps.web.report.ledger import Ledger
from apps.web.dealer.define import DEALER_INCOME_SOURCE
from apilib.monetary import RMB, VirtualCoin
from bson.objectid import ObjectId


# 分离logicalCode
def output_dev_arr(type):
    with open('logicalCode.txt', 'r') as f:
        fileStr = f.read()

    if type == '5':
        r = r"(\d{5})"
    elif type == '6':
        r = r"(\d{6})"
    elif type == 'G':
        r = r"(G\d{6})"
    else:
        print 'type need send'
        return

    targetArr = re.findall(r, fileStr)
    arr = map(lambda t: ''.join(t), targetArr)

    return arr

# 分离iccid
def output_iccid_arr():
    with open('iccid.txt', 'r') as f:
        fileStr = f.read()

    r = r"(\d[bB\d]{18}\d)|(\d[cC\d]{18}\d)"
    targetArr = re.findall(r, fileStr)
    arr = map(lambda t: ''.join(t), targetArr)

    return arr

# 15流量费
def fifteen_fee(logicalCode):
    device = Device.objects(logicalCode=logicalCode).first()
    dealer = Dealer.objects(id=device.ownerId).first()
    dealer.annualTrafficCost = RMB('15.00')
    dealer.trafficCardCost = RMB('15.00')
    dealer.save()
    ds = Device.objects(ownerId=device.ownerId)
    print ds.count()
    for _ in ds:
        _.trafficCardCost = None
        _.save()
        Device.invalid_device_cache(_.devNo)

# 解除设备充值
def unlock_dev_recharge(logicalCode):
    d = Device.objects(logicalCode=logicalCode).first()
    print d.simStatus
    d.simStatus = u'chargedUnupdated'
    d.save()
    Device.invalid_device_cache(d.devNo)

# 重置经销商账号
def reset_dealer_password(username):
    d = Dealer.objects(username=username)
    if d.count() > 1:
        print('more than 1')
        return
    else:
        d = d.first()
    d.set_password('e10adc3949ba59abbe56e057f20f883e')
    d.save()
    d.unlock_login()

# 重置代理商下面的设备年费
def reset_agent_device_traffic_card_cost(username):
    a = Agent.objects(username=username).first()
    ds = Dealer.objects(agentId=str(a.id))
    for _ in ds:
        dds = Device.objects(ownerId=str(_.id))
        for dd in dds:
            dd.trafficCardCost = None
            dd.save()
            Device.invalid_device_cache(dd.devNo)
    print 'done!'

# 创建对公账户
def create_public_merchant(username, accountCode, parentBankName, subBankName, merchantName):
    # 例: create_public_merchant('18458353670', u'33050163742700000876', u'中国建设银行', u'中国建设银行嘉善支行营业部', u'嘉善县博源建设管理有限公司')

    d = Dealer.objects(username=username)
    if d.count() > 1:
        print('more than 1')
        return
    else:
        d = d.first()
    mm = Merchant.objects(ownerId=str(d.id)).first()
    if mm is not None:
        print('existed')
        return
    m = Merchant()
    m.id = ObjectId()
    m.accountType = u'public'
    m.accountCode = accountCode
    m.parentBankName = parentBankName
    m.subBankName = subBankName
    m.cardType = u'借记卡'
    m.merchantName = merchantName
    m.ownerId = str(d.id)
    m.save()
    print 'done!'

# 列表换行输出txt
def write_as_txt(arr, name):
    with open('output_%s.txt' % name, 'w') as f:
        for _ in arr:
            f.write(_ + '\r\n')
    print 'done!'

