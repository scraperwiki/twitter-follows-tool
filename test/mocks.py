import random

def ids(num_ids=None, next_cursor=0, ids=None):
    """fake an 'ids' response: use """
    # {"next_cursor_str": "0", "previous_cursor": 0, "ids": [2151045530, 14284208, 537386838, 72015710, 571602068, 1151009623, 24450319, 41432796, 486759161, 113153902, 105853630, 68366143, 106061815, 103361551, 74178894, 39195990, 56645305, 23512550, 20931484, 22210181, 20104494, 19703625, 17899968, 18673822, 18084850, 1022831, 6549432], "next_cursor": 0, "previous_cursor_str": "0"}
    template = {"previous_cursor": 0, "previous_cursor_str": "0"}

    if ids is None and num_ids is None:
        num_ids = 10
    if ids is None:
       ids = [random.randrange(999999999) for x in range(num_ids)]
    template['ids'] = ids
    template['next_cursor'] = next_cursor
    template['next_cursor_str'] = str(next_cursor)
    return template

def test_ids():
    assert len(ids(10)['ids']) == 10
    assert ids(ids=[1,2,3])['ids'][1] == 2
    assert ids(next_cursor=5)['next_cursor_str'] == '5'
    print "win"
