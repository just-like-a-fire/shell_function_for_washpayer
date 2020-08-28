# -*- coding: utf-8 -*-
#!/usr/bin/env python

# 导包
import re
import random
import datetime
from apps.web.device.models import Device, DriverCode, Group, SIMCard, GroupCacheMgr
from apps.web.dealer.models import Dealer, Merchant, WithdrawRecord, DealerRechargeRecord
from apps.web.agent.models import Agent
from apps.web.management.models import Manager
from apps.web.user.models import Card, MyUser, ConsumeRecord, RechargeRecord, CardRechargeOrder
from apps.web.report.ledger import Ledger
from apps.web.dealer.define import DEALER_INCOME_SOURCE
from apps.web.common.models import OperatorLog
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
    OperatorLog.manual_change_dealer_recharge(logicalCode, {'iccid': d.iccid, 'devNo': d.devNo})
    print 'done!'

# 重置账号
def reset_role_password(username, role):
    if role == 'dealer':
        d = Dealer.objects(username=username)
        if d.count() > 1:
            print('more than 1')
            return
        else:
            d = d.first()
    elif role == 'agent':
        d = Agent.objects(username=username).first()
    elif role == 'manager':
        d = Manager.objects(username=username).first()
    else:
        print 'wrong role'
        return

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
    # callback传write_as_txt
    bbc = []
    for _ in arr:
        try:
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
                onlineStatus = 1
            else:
                onlineStatus = 0

            # 2.检测最近离线
            if dd.offTime != 0:
                lastOfflineTime = datetime.datetime.fromtimestamp(int(str(dd.offTime)[0:10])).strftime("%Y-%m-%d")
            else:
                lastOfflineTime = 0
            
            # 3.检测流量卡充值时间
            simRechargeRcds = DealerRechargeRecord.objects(__raw__={'name': d.ownerId, 'status':'Paid', 'name':{'$regex':str(_)}})
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
                elif d.expireDate is not None:
                    simExpireTime = d.expireDate.strftime("%Y-%m-%d")
                else:
                    simExpireTime = 'None'
            except Exception as e:
                bbc.append(_)
                print _
                continue

            print (_, 'LAST_%s' % lastOfflineTime, 'EXP_%s' % simExpireTime, 'RCG_%s' % simRechargeTime, 'online_%s' % onlineStatus)
            bbc.append(_ + '   ' + '   ' + 'LAST_%s' % lastOfflineTime + '   ' + '   ' + 'EXP_%s' % simExpireTime + '   ' + '   ' + 'RCG_%s' % simRechargeTime + '   ' + '   ' + 'online_%s' % onlineStatus)
        except Exception as e:
            print e

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
    # callback传bbc
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
    c.dealerId = u''
    c.groupId = u''
    c.devNo = u''
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
            _.ruleDict = ruleDict
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
                print 'change success!'
    else:
        d1.username = u2
        d1.save()
        print 'change success!'

# 设置设备的流量卡过期时间
def set_device_sim_expire_time(logicalCode, year, month, day):
    d = Device.objects(logicalCode=logicalCode).first()
    d.simExpireDate = datetime.datetime(year, month, day, 0, 0, 0)
    d.save()
    Device.invalid_device_cache(d.devNo)
    print 'done!'

# 修改设备类型
def change_dev_type(arr, code):
    for _ in arr:
        d = Device.objects(logicalCode=_).first()
        if d.devType == {}:
            print 'device is not register %s' % _
            continue
        else:
            d.devType['code'] = code
            d.save()
            Device.invalid_device_cache(d.devNo)
    print 'done!'

# 热加载最新驱动
def hot_load_new_driver(code):
    d = DriverCode.objects(code=code).first()
    d.adapterVer = str(float(d.adapterVer) + 0.1)
    d.eventerVer = str(float(d.eventerVer) + 0.1)
    d.save()
    print DriverCode.get_type_info(code)
    cache.delete('devType%s' % code)
    print DriverCode.get_type_info(code)
    print 'done!'

# 未分账订单进行分账
def ledger_execute(wxOrderNo):
    r = RechargeRecord.objects(wxOrderNo=wxOrderNo).first()
    group = Group.get_group(r.groupId)
    ledger = Ledger(DEALER_INCOME_SOURCE.RECHARGE, r, group)
    ledger.execute(journal=False, stats=True, check=False)

# 根据手机号码,获取关联id
def get_ids_from_phone(phone):
    ds = Dealer.objects(username=phone)
    a = Agent.objects(username=phone).first()
    m = Manager.objects(username=phone).first()
    tempDict = {}
    arr = [str(_.id) + '_' + _.agentId for _ in ds]
    tempDict.update({'dealer': arr})
    tempDict.update({'agent': str(a.id) if a is not None else ''})
    tempDict.update({'manager': str(m.id) if m is not None else ''})
    return tempDict

# 检测经销商是否刷单
def whether_to_brush(username):
    bbc = []
    d = Dealer.objects(username=username)
    if d.count() > 1:
        print 'more than one _ %s' % username
        return
    elif d.count() == 0:
        print 'no dealer _ %s' % username
        return
    else:
        d = d.first()

    for _ in range(1,101):
        dstr = "Device.objects(__raw__={'washConfig.%s.price': {'$gte': 50}, 'ownerId': str(d.id)})" % _
        rst = eval(dstr)
        if rst.count() != 0:
            for i in rst:
                bbb.append(i.logicalCode)
    return bbc

# 话术

# 01 过期续费
# 您的设备在{}过期的, 最近才进行续费{}, 过期充值的话流量卡已经注销了, 需要给您寄新卡换上去才能正常使用.
# 由于您是过期续费的, 我们不包邮, 默认发顺丰到付, 或者可以选择圆通寄付 10元

# 02 串口不通
# 设备是在线的, 但是发命令主板没有回应, 我先远程重启一下模块试试
# 远程重启模块没用, 建议断电重启一下主板试试
# 如果重启主板也没用的话, 建议替换法排查一下, 把这个模块换到旁边正常运行的设备上, 看一下能否启动旁边正常的设备, 这样可以判断模块是否正常

# 03 设备离线
# 离线, 信号值很差, 流量卡正常的, 信号差导致的离线, 信号只有{}, 看一下天线有没有问题, 如果天线正常, 可能是当地2G网络很差
# 设备是离线的, 最近离线时间是{}, 流量卡是正常的, 看一下模块信号灯是如何闪烁
"""
看一下模块信号灯能否快闪, 如果不是快闪, 按照以下方式排查一下
首先把模块外壳打开
1. 断电重启试一下
2. 把天线重插以及sim卡重插之后, 断电重启试一下
"""
# 设备是离线的, 刚刚离线的, 不超过15分钟, 所以在后台看到还是在线的缓存, 这个需要看一下二维码模块信号灯是如何闪烁的

# 04 怎么登录PC端后台
# 通过电脑浏览器打开http://www.washpayer.com/dealerAdmin/index.html, 然后进行登录即可

# 05 提现以及对公银行账户信息
# 客户提现可以提现到银行卡里面, 在后台可以绑定银行卡, 但是只支持对私银行.
# 对公银行的绑定, 需要客户把对公银行信息以及经销商账号提供给我, 我在后台给客户绑定
# 提现到账时间: 微信 -> 即时到账, 对私银行 -> 1~3天到账, 对公银行 -> 月底到账一次