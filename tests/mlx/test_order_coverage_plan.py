"""用独立列出的答案核对数据生成规则及来源隔离约定。"""
import importlib.util
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parent))
from prepare_order_coverage_plan import example, FAMILIES

GOLD = {
 'business': [{'应付金额':52},{'退款金额':46},{'尾款金额':164},{'运费':6,'应付金额':131},{'建议':'补货','缺货数量':4},{'建议':'人工核查'},{'优先':False},{'建议':'补资料'}],
 'format': [{'订单':'C5-fo-01-00','数量':2,'颜色':'橙色'},{'订单':'C5-fo-02-00','数量':6},{'订单':'C5-fo-03-00','加急':False,'联系人':None},['纸盒','布袋'],{'备注':'橙色款“纪念版”'},{'日期':'2032-05-11'},{'订单':'C5-fo-07-00','数量':0,'备注':'','电话':None},{'订单':'C5-fo-08-00','数量':2}],
 'regression': ['55','95','24',[17,38,44],'12','小周','橙色','2032-09-12'],
 'behavior': [{'应付金额':None,'待补充':['单价']},'资料不足',{'建议':'人工核查'},{'执行状态':'未执行','下一步':'人工确认'},{'订单':'C5-be-05-00','数量':2},{'数量':None,'待确认':['数量']},{'建议':'补资料','待补充':['订单号']},{'订单':'C5-be-08-00','电话':None}],
}

@pytest.mark.parametrize('category,number,expected',[(c,n,x) for c,values in GOLD.items() for n,x in enumerate(values,1)])
def test_independent_reference_answers(category,number,expected):
 assert example(category,number,0)['answer']==expected


def test_threshold_equality_and_conjunction():
 assert example('business',4,1)['answer']=={'运费':0,'应付金额':140}
 assert example('business',7,1)['answer']=={'优先':True}
 assert example('business',7,2)['answer']=={'优先':False}
 assert example('business',8,1)['answer']=={'建议':'人工核查'}
 assert example('business',8,2)['answer']=={'建议':'补货'}
 assert example('business',8,3)['answer']=={'建议':'提交申请'}


def test_each_family_has_distinct_fact_prompts_before_wording_variants():
 for category in FAMILIES:
  for number in range(1,9):
   rows=[example(category,number,case) for case in (0,1,2,3,7)]
   assert len({row['prompt'] for row in rows})==5
   assert len({str(row['facts']) for row in rows})==5
