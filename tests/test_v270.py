"""Regression tests for independently reproduced failures from the 2.69 audit."""
from datetime import datetime
from types import SimpleNamespace
import pickle
import numpy as np
from plo_leak.parser import Hand, Action
from plo_leak.cards import parse_cards


def _cover():
    h = Hand('cover', 'PLO-6', .5, 1, datetime(2026, 1, 1), seats={'H':1, 'V':2},
             stacks={'H':100,'V':20}, hole={'H':parse_cards('As Ah Kd Qd 8c 7c')},
             shown={'V':parse_cards('Ks Kh Jd Td 9c 6c')}, board=parse_cards('Ac 2d 3h 4s 5s'),
             invested={'H':20,'V':20})
    h.actions=[Action('preflop','H','call',1,1),Action('preflop','V','post_bb',1,1),
               Action('flop','V','bet',19,19,True),Action('flop','H','call',19,19),
               Action('turn','H','check'),Action('river','H','check')]
    return h


def test_covering_stack_ignores_later_checks():
    from plo_leak.ev import allin_ev
    got = allin_ev(_cover(),'H')
    assert got is not None and got[2]=='flop'
    assert abs(got[0]-18.01801801801802)<1e-9


def test_no_allin_does_not_become_ev_adjusted():
    from plo_leak.ev import allin_ev
    h=_cover();h.stacks['V']=100
    assert allin_ev(h,'H') is None


def test_sidepot_known_short_stack_cards_remain_dead():
    from plo_leak.ev import allin_ev
    h=Hand('sidepot','PLO-6',.5,1,datetime(2026,1,1),seats={'H':1,'V':2,'S':3},
           stacks={'H':100,'V':100,'S':20},hole={'H':parse_cards('8c 6d 9d Qc 7s 4h')},
           shown={'V':parse_cards('Ks 7h 5d Qh Ah 3c'),'S':parse_cards('Jh Kh Th 5s Js Ad')},
           board=parse_cards('As Qd 5h 7d Ts'),invested={'H':100,'V':100,'S':20})
    h.actions=[Action('turn','S','bet',20,20,True),Action('turn','H','raise',100,100,True),Action('turn','V','call',100,100,True)]
    assert abs(allin_ev(h,'H')[0]-39.333333333333314)<1e-9


def test_each_pot_uses_its_own_lock_street():
    from plo_leak.ev import allin_ev,equities
    h=Hand('locks','PLO-6',.5,1,datetime(2026,1,1),seats={'H':1,'V':2,'S':3},
           stacks={'H':100,'V':100,'S':20},hole={'H':parse_cards('8c 6d 9d Qc 7s 4h')},
           shown={'V':parse_cards('Ks 7h 5d Qh Ah 3c'),'S':parse_cards('Jh Kh Th 5s Js Ad')},
           board=parse_cards('As Qd 5h 7d Ts'),invested={'H':100,'V':100,'S':20})
    h.actions=[Action('flop',p,'call',20,20,p=='S') for p in ('S','H','V')]+[Action('turn',p,'call',80,80,True) for p in ('H','V')]
    holes={**h.shown,**h.hole}
    expected=60*equities(holes,h.board[:3])['H']+160*equities({p:holes[p] for p in ('H','V')},h.board[:4],dead=holes['S'])['H']-100
    assert abs(allin_ev(h,'H')[0]-expected)<1e-9


def test_river_coach_filters_exact_hand_indices():
    from plo_leak.rivercoach import _spots
    ft=SimpleNamespace(t={'rsp':{'hidx':np.array([0,1,2]),'obj':[pickle.dumps({'id':str(i)}) for i in range(3)]}})
    assert [s['id'] for s in _spots(ft,np.array([0,2]))]==['0','2']
    assert _spots(ft,np.array([],int))==[]


def test_sparse_subgroups_have_a_display_schema():
    from plo_leak.report import _display_subgroups
    raw={'title':'test','sub':[{'name':'a','n':10,'mean':-2.0}],'except':['a']}
    got=_display_subgroups([raw])[0]['sub'][0]
    assert got['est']==-2 and got['exempt'] and got['p_pos'] is None
    assert got['estimate_kind']=='rått snitt' and 'est' not in raw['sub'][0]


def test_holdout_small_negative_is_uncertain():
    from plo_leak.holdout import _verdict
    assert _verdict(-.01,10,1000,True)=='osäkert'
    assert _verdict(-3,.1,1000,True)=='håller'
    assert _verdict(-3,.1,1000,False)=='inte oberoende'
    assert _verdict(-3,.1,1000,True,clusters=1)=='för få'
    assert _verdict(3,.1,1000,True)=='håller inte'


def test_holdout_multiplicity_and_frozen_definitions():
    from plo_leak.holdout import _match,_verdict
    r={'id':'x','type':'cutoff','spot':'rfi','pos':'CO','thr':1,'weights':[1,2]}
    assert _match(r,[{**r,'cost':-5,'title':'different display'}]) is not None
    assert _match(r,[{**r,'thr':2}]) is None
    assert _match(r,[{**r,'except':['good']}]) is None
    assert _verdict(-2.1,1,1000,True,1)=='håller'
    assert _verdict(-2.1,1,1000,True,10)=='osäkert'


def test_decision_players_ip_and_pot_update_after_fold():
    from plo_leak.postflop_rows import HEADER,rows_for_hand
    h=Hand('dec','PLO-6',.5,1,datetime(2026,1,1),seats={'V':1,'H':2,'A':3},
           stacks={'V':100,'H':100,'A':100},positions={'V':'SB','H':'BB','A':'BTN'},
           hole={'H':parse_cards('As 5s Kh Qd 4c 3c')},board=parse_cards('Js 9s 2d'))
    h.actions=[Action('preflop',p,'call',10,10) for p in h.seats]+[Action('flop','V','bet',10,10),Action('flop','H','call',10,10),Action('flop','A','fold'),Action('flop','V','raise',30,40),Action('flop','H','call',30,40)]
    rr=[dict(zip(HEADER,r)) for r in rows_for_hand(h,'H',0,light=True)]
    assert [r['players'] for r in rr]==[3,2]
    assert [r['ip'] for r in rr]==[0,1]
    assert rr[1]['pot_at_decision_bb']==80 and rr[1]['pot_after_call_bb']==110
    assert abs(rr[1]['spr_after_call']-50/110)<1e-9


def test_draw_outs_are_distinct_and_not_all_nuts():
    from plo_leak.postflop_rows import draw_outs_info
    got=draw_outs_info(parse_cards('As 5s Kh Qd 4c 3c'),parse_cards('Js 9s 2d'))
    assert got=={'draw_outs':12,'nut_outs':6}


def test_old_exports_do_not_trigger_outs_action_rules():
    from plo_leak.guidelines import postflop_note
    r={'street':'flop','facing':'raise','action':'call','hand':'högt kort','flush_draw':'nöt','straight_outs':4,'facing_allin':0,'eff_stack_bb':80,'pot_bb':30,'to_call_bb':10}
    note=postflop_note(r)
    assert 'jamma' not in note and '13+' not in note  # 2.71: dold – ingen fryst outsregel


def test_blocker_correct_strength_uses_same_sampling_as_beat_n():
    from plo_leak.board import BoardTable
    bt=BoardTable(parse_cards('Js 9s 2d'));h=parse_cards('As 5s Kh Qd 4c 3c')
    assert bt.strength_u(h)==bt.beat_n(h,samples=600)


def test_empty_time_columns_do_not_destroy_identified_regression():
    from plo_leak.fatigue import _fe_coef
    c=np.repeat(np.arange(20),100);t=np.tile(np.linspace(0,.9,100),20);x=(np.tile(np.arange(100),20)>50).astype(float)
    y=4*x+np.random.default_rng(1).normal(size=len(c));blk=(t*2).astype(int)
    X=np.column_stack([x]+[(blk==k).astype(float) for k in range(1,9)])
    b,se=_fe_coef(y,X,c)
    assert abs(b[0]-4)<.5 and np.isfinite(se[0]) and np.isnan(b[-1])


def test_mixed_stakes_are_identified_in_hourly_data():
    from plo_leak.hourly import _block
    n=100;H={'ts':np.arange(n)*60,'clu':np.zeros(n,int),'money':np.ones(n),'ev_m':np.ones(n),'rake_m':np.ones(n),'net':np.ones(n),'ev':np.ones(n),'rake':np.ones(n),'bb':np.tile([1,2],50)}
    assert _block(H,np.arange(n))['mixed_stakes']
    assert not _block(H,np.arange(0,n,2))['mixed_stakes']


def test_running_twice_keeps_the_same_allin_expectation():
    # Average payout over two runouts has the same expectation as one runout.
    from plo_leak.ev import allin_ev
    h = _cover()
    single = allin_ev(h, 'H')
    h.run_twice = True
    assert allin_ev(h, 'H') == single


def test_vector_outs_match_an_exhaustive_board_pair_reference():
    import random
    from plo_leak.postflop_rows import draw_outs_info, _has_straight
    from plo_leak.board import BoardTable
    rnd = random.Random(270)
    deck = [(r, s) for r in range(2, 15) for s in 'cdhs']
    for k in range(12):
        cs = rnd.sample(deck, 10 if k % 2 else 9)
        hole, board = cs[:6], cs[6:]
        hits = []
        for c in deck:
            if c in cs:
                continue
            b = board + [c]
            if _has_straight([x[0] for x in hole], [x[0] for x in b]) or any(sum(x[1] == s for x in hole) >= 2 and sum(x[1] == s for x in b) >= 3 for s in 'cdhs'):
                hits.append(c)
        expected_nuts = sum(BoardTable(board + [c]).beat_frac(hole) == 0 for c in hits)
        assert draw_outs_info(hole, board) == {'draw_outs': len(hits), 'nut_outs': expected_nuts}


def test_coach_uses_selected_total_fees_and_keeps_advice_hypothetical(monkeypatch):
    import plo_leak.rivercoach as rc
    seen = {}
    class Fees:
        def fit_arrays(self, pot, fee, bb):
            seen['fees'] = np.asarray(fee)
            return self
    def analyze(spots, hero, fees, total):
        seen['spots'] = spots
        seen['total'] = total
        return SimpleNamespace(spots=len(spots), decisions=[], calibration={}, findings=[])
    monkeypatch.setattr(rc, 'FeeModel', Fees)
    monkeypatch.setattr(rc, 'analyze_spots', analyze)
    monkeypatch.setattr(rc, 'component_ok', lambda *a: True)
    ft = SimpleNamespace(n=1000, H={'pot':np.ones(1000)*100,'pot_fee':np.ones(1000)*3,
                                  'rake':np.zeros(1000),'bb':np.ones(1000)},
                         t={'rsp':{'hidx':np.arange(1000),'obj':[pickle.dumps({'id':str(i)}) for i in range(1000)]}})
    got = rc.coach(SimpleNamespace(ft=ft, rows=np.arange(500)), 'H')
    assert len(seen['spots']) == 500 and seen['total'] == 500
    assert seen['fees'].tolist() == [3.0]*500
    assert got['calibrated']['mot_bet'] and not any(got['ok'].values())


def test_holdout_split_is_between_whole_sessions(monkeypatch):
    import plo_leak.holdout as ho
    import plo_leak.aggregate as aggregate
    import plo_leak.analyses as analyses
    import plo_leak.practice as practice
    H = {'ts':np.arange(6), 'clu':np.array([0,0,0,1,1,1])}
    ft = SimpleNamespace(H=H, n=6)
    st = SimpleNamespace(ft=ft, rows=np.arange(6), hands_by_id=None)
    selected = {}
    def stats(ft, mask, hero, lookup):
        selected['mask'] = mask
        return SimpleNamespace()
    monkeypatch.setattr(aggregate, 'build_stats', stats)
    monkeypatch.setattr(analyses, 'REGISTRY', {k:{'fn':lambda *a: {}} for k in ho.DISCOVERY})
    monkeypatch.setattr(practice, 'build_rules', lambda *a: {'rules':[]})
    doc, cut, old, new = ho._discover_old(st, 'H', None, None)
    assert (cut, old, new) == (3, 3, 3)
    assert selected['mask'].tolist() == [True,True,True,False,False,False]


def test_collinear_time_and_loss_cannot_be_claimed_as_separate_effects():
    from plo_leak.fatigue import _fe_coef
    c = np.repeat(np.arange(20),100)
    x = (np.tile(np.arange(100),20) >= 50).astype(float)
    z = (np.tile(np.arange(100),20) % 7 == 0).astype(float)
    y = 2*x + 3*z + np.random.default_rng(5).normal(0,.1,len(c))
    beta, se = _fe_coef(y,np.column_stack([x,x,z]),c)
    assert np.isnan(beta[0]) and np.isnan(beta[1])
    assert abs(beta[2]-3)<.1 and np.isfinite(se[2])


# ---------------- 2.71 ----------------
def _v271_hands():
    from pathlib import Path
    from plo_leak.parser import parse_text
    p = Path(__file__).parent / 'v271' / 'gg_v271_effective.txt'
    return {h.id: h for h in parse_text(p.read_text(encoding='utf-8'))}


def test_v271_call_capped_at_hero_stack():
    """Granskningen 2026-11-13: exporten visade 190/202/132 bb syn; Hero hade bara 43/61/41,5 bb kvar."""
    from plo_leak.postflop_rows import HEADER, rows_for_hand
    H = _v271_hands()
    want = {'OM115885731': (42.96, 292.92, 147.39), 'OM115916355': (60.69, 323.88, 141.81),
            'OM115961216': (41.5, 215.0, 90.5)}
    for hid, (call, pot_after, ret) in want.items():
        rows = [dict(zip(HEADER, r)) for r in rows_for_hand(H[hid], 'Hero', 0.0, light=True)]
        c = [r for r in rows if r['action'] == 'call'][-1]
        assert abs(c['to_call_bb'] - call) < 0.01 and abs(c['effective_risk_bb'] - call) < 0.01
        assert abs(c['pot_after_call_bb'] - pot_after) < 0.01 and abs(c['uncalled_return_bb'] - ret) < 0.01
        assert c['raw_amount_bb'] > c['to_call_bb']


def test_v271_river_overbet_effective_risk():
    """OM115693387: 135 $ i 225 $, motståndaren har 82 $ kvar → effektiv risk 82 $ = 36,4 % av potten."""
    from plo_leak.postflop_rows import HEADER, rows_for_hand
    rows = [dict(zip(HEADER, r)) for r in rows_for_hand(_v271_hands()['OM115693387'], 'Hero', 0.0, light=True)]
    r = [x for x in rows if x['street'] == 'river' and x['action'] == 'bet'][0]
    assert abs(r['raw_amount_bb'] - 67.5) < 0.01 and abs(r['effective_risk_bb'] - 41.0) < 0.01
    assert abs(r['uncalled_return_bb'] - 26.5) < 0.01 and abs(r['effective_bet_pct'] - 36.4) < 0.05
    assert r['draw_calc_status'] == 'river'


def test_v271_uncapped_multiway_call_unchanged():
    from plo_leak.postflop_rows import HEADER, rows_for_hand
    rows = [dict(zip(HEADER, r)) for r in rows_for_hand(_v271_hands()['OM115711244'], 'Hero', 0.0, light=True)]
    c = rows[-1]
    assert abs(c['to_call_bb'] - 127.12) < 0.01 and c['uncalled_return_bb'] == 0.0


def test_v271_draw_calc_status_values():
    from plo_leak.postflop_rows import HEADER
    assert 'draw_calc_status' in HEADER and 'effective_risk_bb' in HEADER and 'raw_amount_bb' in HEADER


def test_v271_forward_freeze_date_and_metod():
    from plo_leak.forward import FREEZE_DATE, freeze_ts
    from plo_leak.dataexport import METOD
    assert FREEZE_DATE == '2026-11-13' and freeze_ts() > 1_790_000_000
    for k in ('hand_id', 'session', 'effective_risk_bb', 'draw_calc_status', 'Rakeback ingår inte', 'frysta 2026-11-13'):
        assert k in METOD


def test_v271_hourly_summary_rows_overlap():
    import numpy as np
    from types import SimpleNamespace
    from plo_leak import hourly
    # två pass; pass 2 blandar nivåer → nivåtimmar överlappar
    ts = np.array([0, 60, 120, 180, 10000, 10060, 10120, 10180] * 1, dtype=np.int64) + 1_790_000_000
    n = len(ts)
    H = {"ts": ts, "clu": np.array([0, 0, 0, 0, 1, 1, 1, 1]), "money": np.ones(n), "ev_m": np.ones(n), "rake_m": np.zeros(n),
         "net": np.ones(n), "ev": np.ones(n), "rake": np.zeros(n), "bb": np.array([1, 1, 1, 1, 1, 2, 1, 2.]),
         "stake": np.array([0, 0, 0, 0, 0, 1, 0, 1])}
    b = hourly._block(H, np.arange(n))
    assert b["mixed_stakes"] and b["sessions"] == 2 and b["hours"] > 0
    assert hourly.HOURLY_HEADER[0] == 'level' and 'rakeback' in hourly.HOURLY_HEADER
