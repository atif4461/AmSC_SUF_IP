
import arrow
import fixtures

def test_basic():
    print("Creating dummy hit data in pandas")

    hits_df = fixtures.make_dummy_hits_df()
    print (hits_df)

    assert(1 == fixtures.increment(1))


