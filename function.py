# -*- coding: utf-8 -*-
#!/usr/bin/env python

# 导包
import re
import datetime
from apps.web.device.models import Device, DriverCode, Group, SIMCard, GroupCacheMgr
from apps.web.dealer.models import Dealer, Merchant, WithdrawRecord, DealerRechargeRecord
from apps.web.agent.models import Agent
from apps.web.user.models import Card, MyUser, ConsumeRecord, RechargeRecord, CardRechargeOrder
from apps.web.report.ledger import Ledger
from apps.web.dealer.define import DEALER_INCOME_SOURCE
from apilib.monetary import RMB, VirtualCoin
from bson.objectid import ObjectId
from django.core.cache import cache

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
    print 'done!'

# 解除设备充值
def unlock_dev_recharge(logicalCode):
    d = Device.objects(logicalCode=logicalCode).first()
    print 'before_%s' % d.simStatus
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
    print 'done!'

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
def create_public_merchant(username, accountCode, parentBankName, subBankName, merchantName, dealerId=None):
    # 例: create_public_merchant('18458353670', u'33050163742700000876', u'中国建设银行', u'中国建设银行嘉善支行营业部', u'嘉善县博源建设管理有限公司')

    if dealerId is not None:
        d = Dealer.objects(id=dealerId).first()
    else:
        d = Dealer.objects(username=username)
        if d.count() > 1:
            print('more than 1')
            return
        else:
            d = d.first()

    mm = Merchant.objects(ownerId=str(d.id)).first()
    if mm is not None:
        mm.ownerId = u''
        mm.save()
        print 'indeed.'
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
    with open('out_%s.txt' % name, 'w') as f:
        for _ in arr:
            f.write(_ + '\r\n')
    print 'done!'

# 检测设备是否需要寄卡
def is_need_new_sim(arr, callback=None):
    bbc = []
    for _ in arr:
        d = Device.objects(logicalCode=_).first()

        try:
            dd = Device.get_dev(d.devNo)
        except Exception as e:
            bbc.append(_)
            print _
            continue

        # 不存在的设备跳过
        if d is None:
            continue

        # 1.检测是否在线
        if dd.online != 0:
            continue

        # 2.检测最近离线
        if dd.offTime != 0:
            lastOfflineTime = datetime.datetime.fromtimestamp(int(str(dd.offTime)[0:10])).strftime("%Y-%m-%d")
        else:
            lastOfflineTime = 0
        
        # 3.检测流量卡充值时间
        simRechargeRcds = DealerRechargeRecord.objects(__raw__={'dealerId': d.ownerId, 'status':'Paid'})
        # 循环走完默认拿最后一次的充值时间
        if simRechargeRcds.count() > 0:
            for s in simRechargeRcds:
                # todo 少数情况有bug, 最好精确匹配
                if _ in s.name:
                    simRechargeTime = s.finishedTime.strftime("%Y-%m-%d")
        else:
            simRechargeTime = 0

        try:
            # 4.检测设备过期时间
            if d.simExpireDate is not None:
                simExpireTime = d.simExpireDate.strftime("%Y-%m-%d")
            else:
                simExpireTime = d.expireDate.strftime("%Y-%m-%d")
        except Exception as e:
            bbc.append(_)
            print _
            continue

        print (_, 'LAST_%s' % lastOfflineTime, 'EXP_%s' % simExpireTime, 'RCG_%s' % simRechargeTime)
        bbc.append(_ + '   ' + '   ' + 'LAST_%s' % lastOfflineTime + '   ' + '   ' + 'EXP_%s' % simExpireTime + '   ' + '   ' + 'RCG_%s' % simRechargeTime)

        if callback is not None:
            callback(bbc, '%s' % str(random.randint(1,100)))

    return bbc

# 删除乱注册的经销商
def delete_dealer(username):
    d = Dealer.objects(username=username)
    if d.count() > 1:
        print 'more than one _ %s' % username
        return
    elif d.count() == 0:
        print 'no dealer _ %s' % username
        return
    else:
        d = d.first()

    ds = Device.objects(ownerId=str(d.id))
    if ds.count() > 0:
        print 'dealer has devices _ %s' % username
        for _ in ds:
            print _.logicalCode
        return

    gs = Group.objects(ownerId=str(d.id))
    if gs.count() > 0:
        print 'dealer has groups _ %s' % username
        return

    rs = RechargeRecord.objects(ownerId=str(d.id))
    if rs.count() > 0:
        print 'dealer has recharge records _ %s' % username
        return

    cs = ConsumeRecord.objects(ownerId=str(d.id))
    if cs.count() > 0:
        print 'dealer has consume records _ %s' % username
        return

    d.delete()
    print 'dealer is deleted _ %s' % username
    return 1

# 验证SIM卡是否是上个月底过期的
def verify_last_month_sim(arr, year, month, day, callback=None):
    arr_list = []
    for _ in arr:
        s = SIMCard.objects(iccid=_).first()
        if s is not None and s.expireTime == datetime.datetime(year, month, day, 0, 0, 0):
            print s.imsi
            arr_list.append(s.imsi)

    if callback is not None:
        callback(bbc, '%s' % str(random.randint(1,100)))

    return arr_list

# 重置充电卡
def reset_recharge_card(cardNo):
    c = Card.objects(cardNo=cardNo)
    if c.count() > 1:
        print 'more than 1'
        return
    elif c.count() == 0:
        print 'no card'
        return
    else:
        c = c.first()

    c.openId = u''
    c.nickName = u''
    c.status = u'active'
    c.frozen = False
    c.phone = u''
    c.cardName = u''
    c.managerialAppId = u''
    c.managerialOpenId = u''
    c.save()
    print 'done!'

# 解锁续充
def unlock_payable_while_busy(logicalCode):
    d = Device.objects(logicalCode=logicalCode).first()
    if d is None:
        print 'no device'
        return

    if d.devType == {}:
        print 'no register'
        return

    d.devType['payableWhileBusy'] = True
    d.save()
    Device.invalid_device_cache(d.devNo)
    
# 里歌的端午节充值卡优惠批量设置
def leeger_group_card_discount(dealerId, passedGroupIdList, ruleDict):

    # 例: leeger_group_card_discount('5bbc30de8732d662044c2d73', ['5cff6be20030485cf9ed481e', '5d64e56e003048437d4721f1', '5dc7be3de305f75cd473233d', '5d3289890030480d882827ed', '5d3cff01003048414826caef', '5d47d59c0030485cb7910183', '5d5dff930030483729291d26', '5d7f2f05e305f75cd4997189', '5d7f32aae305f75cd49c573b', '5d7f4555e305f75cd4ab1364'], {"50":60.0, "100":130.0})
    d = Dealer.objects(id=dealerId).first()
    if d is None:
        print 'dealer is None'
        return

    gs = Group.objects(ownerId=dealerId)
    for _ in gs:
        groupId = str(_.id)
        if groupId in passedGroupIdList:
            print _.groupName
            continue
        else:
            _.cardRuleDict = ruleDict
            _.save()
            GroupCacheMgr.invalid_group_cache(groupId)
    print 'done!'

# 修改经销商账号
def change_dealer_username(u1,u2, callback=None):
    # callback传入delete_dealer
    d1 = Dealer.objects(username=u1)
    if d1.count() == 0:
        print 'u1 no dealer'
        return
    elif d1.count() > 1:
        print 'u1 has more than 1 dealers'
        return
    else:
        d1 = d1.first()

    d2 = Dealer.objects(username=u2)
    if d2.count() != 0:
        print 'not law'
        if callback is not None:
            result = callback(u2)
            if result == 1:
                d1.username = u2
                d1.save()
                print 'done!'
    else:
        d1.username = u2
        d1.save()
        print 'done!'

