package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

class ConsultationForumAuth extends Simulation {

  val httpProtocol = http
    .baseURL(C2corgConf.forum_url)
    .inferHtmlResources(C2corgConf.black_list, WhiteList())
    .acceptHeader("application/json, text/javascript, */*; q=0.01")
    .acceptEncodingHeader("gzip, deflate")

  val scn = scenario("ConsultationForumAuth")
    .exec(Forum.init)
    .pause(2)
    .exec(Auth.loginForum)
    .pause(8)
    .exec(Forum.post)

  val numUsers = Integer.getInteger("users", 100)
  val rampSec = Integer.getInteger("ramp", 300)

  setUp(scn.inject(rampUsers(numUsers) over (rampSec seconds))).protocols(httpProtocol)

}
