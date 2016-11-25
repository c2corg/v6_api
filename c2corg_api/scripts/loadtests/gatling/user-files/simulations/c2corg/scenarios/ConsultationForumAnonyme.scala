package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

class ConsultationForumAnonyme extends Simulation {

  val httpProtocol = http
    .baseURL(C2corgConf.forum_url)
    .inferHtmlResources(C2corgConf.black_list, WhiteList())
    .acceptHeader("application/json, text/javascript, */*; q=0.01")
    .acceptEncodingHeader("gzip, deflate")

  val scn = scenario("ConsultationForumAnonyme")
    .exec(Forum.init)
    .pause(1)
    .exec(Forum.open)
    .pause(6)
    .exec(Forum.scroll)
    .pause(8)
    .exec(Forum.scroll)
    .pause(1)
    .exec(Topic.open)
    .pause(24)
    .exec(Topic.scroll)

  val numUsers = Integer.getInteger("users", 100)
  val rampSec = Integer.getInteger("ramp", 300)

  setUp(scn.inject(rampUsers(numUsers) over (rampSec seconds))).protocols(httpProtocol)

}
